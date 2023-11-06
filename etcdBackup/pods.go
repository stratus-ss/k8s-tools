package main

import (
	"fmt"
	"strings"

	batchv1 "k8s.io/api/batch/v1"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

func createBackupPodNoPVC(nodeName string, projectName string, imageURL string, jobName string, serviceAccountName string, taintName string, debug bool, debug_header string, ocpBinaryPath string) *batchv1.Job {
	// createBackupPodNoPVC creates a Kubernetes Job that runs a backup script on a specific node and then moves the resulting tarball to a PVC.
	// Args:
	// 		nodeName: the name of the node where the backup should run
	// 		projectName: the name of the Kubernetes project where the backup should be stored
	// 		imageURL: the URL of the Docker image to use for the backup container
	// 		jobName: the name of the Kubernetes Job to create
	// 		serviceAccountName: the name of the Kubernetes service account to use for the backup
	// 		taintName: the name of the taint to apply to the node before running the backup
	// 		debug: whether or not to enable debugging mode
	// 		debugHeader: the header to use when debugging
	// 		ocpBinaryPath: the path to the OpenShift binary
	// Creates a debug pod from the nodeName passed in
	// Pod is based on the ose-cli pod and runs an etcd backup
	// in the future may take namespace and other arguments to make this more flexible
	// this command should be run as a prefix to all commands in the debug pod
	cmd := ""
	if ocpBinaryPath == "" {
		cmd = "oc debug node/" + nodeName + " -- chroot /host"
	} else {
		cmd = ocpBinaryPath + "/oc debug node/" + nodeName + " -- chroot /host"
	}
	// create a temporary tarball which will eventually be moved to the pod's PVC
	tempTarball := "/tmp/etcd_backup.tar.gz"
	tempBackupDir := "/tmp/assets/backup"
	cleanupCMD := cmd + " rm -rfv " + tempBackupDir
	backupCMD := cmd + " /usr/local/bin/cluster-backup.sh " + tempBackupDir
	tarCMD := cmd + " tar czf " + tempTarball + " " + tempBackupDir

	taintKey := taintName
	taintVal := ""

	if strings.Contains(taintName, "=") {
		splitVar := strings.Split(taintName, "=")
		taintKey = splitVar[0]
		taintVal = splitVar[1]
	}

	// using cat to stream the tarball from one host to another is one way to transfer without mounting
	// any mounts on the debug host
	jobSpec := &batchv1.Job{
		ObjectMeta: metav1.ObjectMeta{
			Name:      jobName,
			Namespace: projectName,
		},
		Spec: batchv1.JobSpec{
			PodFailurePolicy: &batchv1.PodFailurePolicy{
				Rules: []batchv1.PodFailurePolicyRule{
					{
						OnExitCodes: &batchv1.PodFailurePolicyOnExitCodesRequirement{
							Operator:      batchv1.PodFailurePolicyOnExitCodesOpIn,
							Values:        []int32{1},
							ContainerName: &jobName,
						},
						Action: batchv1.PodFailurePolicyActionFailJob,
					},
				},
			},
			Template: corev1.PodTemplateSpec{
				Spec: corev1.PodSpec{
					Tolerations: []corev1.Toleration{
						{
							Key:   taintKey,
							Value: taintVal,
						},
					},
					Containers: []corev1.Container{
						{
							Name:            jobName,
							Image:           imageURL,
							ImagePullPolicy: corev1.PullIfNotPresent,
							Command: []string{
								"/bin/bash",
								"-c",
								backupCMD + " && " + tarCMD + " && " + cleanupCMD,
							},
						},
					},
					RestartPolicy:      corev1.RestartPolicyNever,
					ServiceAccountName: serviceAccountName,
					NodeSelector: map[string]string{
						"node-role.kubernetes.io/master": "",
					},
				},
			},
		},
	}

	return (jobSpec)
}

func createBackupPodWithPVC(nodeName string, projectName string, imageURL string, firstPVCName string, secondPVCName string, jobName string, serviceAccountName string, taintName string, debug bool, debugHeader string, ocpBinaryPath string) *batchv1.Job {
	// createBackupPodWithPVC creates a backup pod with a PVC
	// Args:
	// 		nodeName: The name of the node to create the backup pod on
	// 		projectName: The name of the project to create the backup pod in
	// 		imageURL: The URL of the image to use for the backup pod
	// 		firstPVCName: The name of the first PVC to use for the backup pod
	// 		secondPVCName: The name of the second PVC to use for the backup pod
	// 		jobName: The name of the job to create
	// 		serviceAccountName: The name of the service account to use for the backup pod
	// 		taintName: The name of the taint to add to the backup pod
	// 		debug: Whether or not to enable debug mode
	// 		debugHeader: The header to use for debug output
	// 		ocpBinaryPath: The path to the OCP binary
	// Creates a debug pod from the nodeName passed in
	// Pod is based on the ose-cli pod and runs an etcd backup
	// in the future may take namespace and other arguments to make this more flexible
	// this command should be run as a prefix to all commands in the debug pod
	cmd := ""
	if ocpBinaryPath == "" {
		cmd = "oc debug node/" + nodeName + " -- chroot /host"
	} else {
		cmd = ocpBinaryPath + "/oc debug node/" + nodeName + " -- chroot /host"
	}
	// create a temporary tarball which will eventually be moved to the pod's PVC
	tempTarball := "/tmp/etcd_backup.tar.gz"
	tempBackupDir := "/tmp/assets/backup"
	// generate a random UUID for the job name
	backupCMD := cmd + " /usr/local/bin/cluster-backup.sh " + tempBackupDir
	tarCMD := cmd + " tar czf " + tempTarball + " " + tempBackupDir

	priv := true

	taintKey := taintName
	taintVal := ""

	if strings.Contains(taintName, "=") {
		splitVar := strings.Split(taintName, "=")
		taintKey = splitVar[0]
		taintVal = splitVar[1]
	}

	// using cat to stream the tarball from one host to another is one way to transfer without mounting
	// any mounts on the debug host
	copyFirstTarball := cmd + " cat " + tempTarball + " > /backups/backup_$(date +%Y-%m-%d_%H-%M_%Z).db.tgz"
	cleanupCMD := cmd + " rm -rfv " + tempBackupDir + " && " + cmd + " rm -f " + tempTarball
	fullBackupCMD := []string{
		"/bin/bash",
		"-c",
		backupCMD + " && sleep 3 && " + tarCMD + " && sleep 3 && " + copyFirstTarball + " && sleep 3 && " + cleanupCMD,
	}

	// We need to define the mount and volume before hand so that in the event there are 2 mount points
	// We can create the definition for the mounts before the pod definition and just pass the mounts in
	volumeDef := []corev1.Volume{}
	mountDef := []corev1.VolumeMount{
		corev1.VolumeMount{
			Name:      "etcd-backup-mount",
			MountPath: "/backups",
		},
	}
	if firstPVCName != "" {
		if debug {
			fmt.Printf("%s First PVC Name: %s\n", debugHeader, firstPVCName)
		}
		volumeDef = []corev1.Volume{
			{
				Name: "etcd-backup-mount",
				VolumeSource: corev1.VolumeSource{
					PersistentVolumeClaim: &corev1.PersistentVolumeClaimVolumeSource{
						ClaimName: firstPVCName,
					},
				},
			},
		}
	}

	if secondPVCName != "" {
		if debug {
			fmt.Printf("%s Second PVC Name: %s\n", debugHeader, secondPVCName)
		}
		volumeDef = []corev1.Volume{
			{
				Name: "etcd-backup-mount",
				VolumeSource: corev1.VolumeSource{
					PersistentVolumeClaim: &corev1.PersistentVolumeClaimVolumeSource{
						ClaimName: secondPVCName,
					},
				},
			},
		}
	}

	// if we have both a dynamic and an NFS PVC defined we want to define the pod to have both
	if firstPVCName != "" && secondPVCName != "" {
		copySecondTarballCMD := cmd + " cat " + tempTarball + " > /backups2/backup_$(date +%Y-%m-%d_%H-%M_%Z).db.tgz"
		fullBackupCMD = []string{
			"/bin/bash",
			"-c",
			backupCMD + " && sleep 3 && " + tarCMD + " && sleep 3 && " + copySecondTarballCMD + " && sleep 3 && " + cleanupCMD,
		}
		mountDef = []corev1.VolumeMount{
			corev1.VolumeMount{
				Name:      "etcd-backup-mount",
				MountPath: "/backups",
			},
			corev1.VolumeMount{
				Name:      "etcd-backup-mount2",
				MountPath: "/backups2",
			},
		}
		volumeDef = []corev1.Volume{
			{
				Name: "etcd-backup-mount",
				VolumeSource: corev1.VolumeSource{
					PersistentVolumeClaim: &corev1.PersistentVolumeClaimVolumeSource{
						ClaimName: firstPVCName,
					},
				},
			},
			{
				Name: "etcd-backup-mount2",
				VolumeSource: corev1.VolumeSource{
					PersistentVolumeClaim: &corev1.PersistentVolumeClaimVolumeSource{
						ClaimName: secondPVCName,
					},
				},
			},
		}
	}

	jobSpec := &batchv1.Job{
		ObjectMeta: metav1.ObjectMeta{
			Name:      jobName,
			Namespace: projectName,
		},
		Spec: batchv1.JobSpec{
			PodFailurePolicy: &batchv1.PodFailurePolicy{
				Rules: []batchv1.PodFailurePolicyRule{
					{
						OnExitCodes: &batchv1.PodFailurePolicyOnExitCodesRequirement{
							Operator:      batchv1.PodFailurePolicyOnExitCodesOpIn,
							Values:        []int32{1},
							ContainerName: &jobName,
						},
						Action: batchv1.PodFailurePolicyActionFailJob,
					},
				},
			},
			Template: corev1.PodTemplateSpec{
				Spec: corev1.PodSpec{
					Tolerations: []corev1.Toleration{
						{
							Key:   taintKey,
							Value: taintVal,
						},
					},
					Containers: []corev1.Container{
						{
							Name:            jobName,
							Image:           imageURL,
							ImagePullPolicy: corev1.PullIfNotPresent,
							Command:         fullBackupCMD,
							VolumeMounts:    mountDef,
							SecurityContext: &corev1.SecurityContext{
								Privileged: &priv,
							},
						},
					},
					RestartPolicy:      corev1.RestartPolicyNever,
					ServiceAccountName: serviceAccountName,
					Volumes:            volumeDef,

					NodeSelector: map[string]string{
						"node-role.kubernetes.io/master": "",
					},
				},
			},
		},
	}

	return (jobSpec)
}
