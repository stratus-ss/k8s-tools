package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"log"
	"math/rand"
	"os"
	"os/exec"
	"os/user"
	"strings"
	"time"

	batchv1 "k8s.io/api/batch/v1"
	corev1 "k8s.io/api/core/v1"
	v1 "k8s.io/api/core/v1"
	rbac "k8s.io/api/rbac/v1"
	"k8s.io/apimachinery/pkg/api/resource"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/tools/clientcmd"
)

func randomString(length int) string {
	// Generate a random uuid to attach to the pod name
	// so that this can be called multiple times without conflicting with previous runs
	rand.Seed(time.Now().UnixNano())
	b := make([]byte, length)
	rand.Read(b)
	return fmt.Sprintf("%x", b)[:length]
}

func createClusterBackupRole(namespaceName string, client *kubernetes.Clientset) {
	// Create the privileged role
	roleName := "cluster-etcd-backup"
	nodeVerbs := []string{"get", "list"}
	apiGroup := []string{""}
	nodeResources := []string{"nodes"}
	podVerbs := []string{"get", "list", "create", "delete", "watch"}
	podResources := []string{"pods", "pods/log"}
	rules := []rbac.PolicyRule{rbac.PolicyRule{Verbs: nodeVerbs, APIGroups: apiGroup, Resources: nodeResources}, rbac.PolicyRule{Verbs: podVerbs, APIGroups: apiGroup, Resources: podResources}}
	clusterRole := &rbac.ClusterRole{
		ObjectMeta: metav1.ObjectMeta{
			Name: roleName,
		},
		Rules: rules,
	}

	_, err := client.RbacV1().ClusterRoles().Update(context.TODO(), clusterRole, metav1.UpdateOptions{})

	if err != nil {
		panic(err)
	}

}
func createClusterPriviligedRole(namespaceName string, client *kubernetes.Clientset) {
	// Create the privileged role
	roleName := "system:openshift:scc:privileged"
	verbs := []string{"use"}
	apiGroup := []string{"security.openshift.io"}
	resources := []string{"securitycontextconstraints"}
	resourceNames := []string{"privileged"}
	rules := []rbac.PolicyRule{rbac.PolicyRule{Verbs: verbs, APIGroups: apiGroup, Resources: resources, ResourceNames: resourceNames}}
	clusterRole := &rbac.ClusterRole{
		ObjectMeta: metav1.ObjectMeta{
			Name: roleName,
		},
		Rules: rules,
	}

	_, exist_err := client.RbacV1().ClusterRoles().Get(context.TODO(), roleName, metav1.GetOptions{})
	if exist_err != nil {
		_, err := client.RbacV1().ClusterRoles().Create(context.TODO(), clusterRole, metav1.CreateOptions{})

		if err != nil {
			panic(err)
		}
	}
}

func createClusterPriviligedRoleBinding(namespaceName string, serviceAccountName string, client *kubernetes.Clientset) {
	// Create the privileged role
	roleName := "etcd-backup-privileged"
	subjects := []rbac.Subject{rbac.Subject{Kind: "ServiceAccount", Name: serviceAccountName, Namespace: namespaceName}}
	roleRefs := rbac.RoleRef{APIGroup: "rbac.authorization.k8s.io", Kind: "ClusterRole", Name: "system:openshift:scc:privileged"}
	clusterRoleBinding := &rbac.ClusterRoleBinding{
		ObjectMeta: metav1.ObjectMeta{
			Name: roleName,
		},
		Subjects: subjects,
		RoleRef:  roleRefs,
	}

	_, err := client.RbacV1().ClusterRoleBindings().Update(context.TODO(), clusterRoleBinding, metav1.UpdateOptions{})
	if err != nil {
		panic(err)

	}
}

func createClusterBackupRoleBinding(namespaceName string, serviceAccountName string, client *kubernetes.Clientset) {
	// Create the privileged role
	subjects := []rbac.Subject{rbac.Subject{Kind: "ServiceAccount", Name: serviceAccountName, Namespace: namespaceName}}
	roleRefs := rbac.RoleRef{APIGroup: "rbac.authorization.k8s.io", Kind: "ClusterRole", Name: "cluster-etcd-backup"}
	clusterRoleBinding := &rbac.ClusterRoleBinding{
		ObjectMeta: metav1.ObjectMeta{
			Name: serviceAccountName,
		},
		Subjects: subjects,
		RoleRef:  roleRefs,
	}

	_, err := client.RbacV1().ClusterRoleBindings().Update(context.TODO(), clusterRoleBinding, metav1.UpdateOptions{})

	if err != nil {
		panic(err)
	}

}

func createServiceAccount(namespaceName string, serviceAccountName string, client *kubernetes.Clientset) {
	serviceAccount := &corev1.ServiceAccount{
		ObjectMeta: metav1.ObjectMeta{
			Name:      serviceAccountName,
			Namespace: namespaceName,
		},
	}
	_, exist_err := client.CoreV1().ServiceAccounts(namespaceName).Get(context.TODO(), serviceAccountName, metav1.GetOptions{})
	if exist_err != nil {
		_, err := client.CoreV1().ServiceAccounts(namespaceName).Create(context.TODO(), serviceAccount, metav1.CreateOptions{})

		if err != nil {
			panic(err)
		}
	}
}

func createProject(namespaceName string, serviceAccountName string, debug bool, debug_header string, client *kubernetes.Clientset) {
	// Check to see if project exists
	// If project doesn't exist, create it
	// returns an error if it fails
	namespace := &corev1.Namespace{
		ObjectMeta: metav1.ObjectMeta{
			Name: namespaceName,
			Labels: map[string]string{
				"name": namespaceName,
			},
		},
	}
	_, exist_err := client.CoreV1().Namespaces().Get(context.TODO(), namespaceName, metav1.GetOptions{})
	if debug {
		fmt.Printf("%s project: %s did not exist\n", debug_header, namespaceName)
		fmt.Printf("%s creating the project %s\n", debug_header, namespaceName)
	}
	if exist_err != nil {
		_, createNamespaceError := client.CoreV1().Namespaces().Create(context.TODO(), namespace, metav1.CreateOptions{})

		if createNamespaceError != nil {
			fmt.Println("Failed to create namespace")
			panic(createNamespaceError)
		}
	}
	fmt.Println("Creating service account...")
	createServiceAccount(namespaceName, serviceAccountName, client)
	fmt.Println("Ensuring that ClusterRole exists...")
	createClusterPriviligedRole(namespaceName, client)
	createClusterBackupRole(namespaceName, client)

	fmt.Println("Checking to make sure ClusterRole is applied to " + serviceAccountName + " service account...")
	createClusterPriviligedRoleBinding(namespaceName, serviceAccountName, client)
	createClusterBackupRoleBinding(namespaceName, serviceAccountName, client)

}

func createBackupPodNoPVC(nodeName string, projectName string, imageURL string, jobName string, serviceAccountName string, taintName string, debug bool, debug_header string, ocpBinaryPath string) *batchv1.Job {
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

func createBackupPodWithPVC(nodeName string, projectName string, imageURL string, firstPVCName string, secondPVCName string, jobName string, serviceAccountName string, taintName string, debug bool, debug_header string, ocpBinaryPath string) *batchv1.Job {
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
			fmt.Printf("%s First PVC Name: %s\n", debug_header, firstPVCName)
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
			fmt.Printf("%s Second PVC Name: %s\n", debug_header, secondPVCName)
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

func createPersistentNFSVolume(namespaceName string, nfsServer string, nfsPath string, debug bool, debug_header string, volumeName string, claimName string, client *kubernetes.Clientset) {
	// This assumes the creation of an NFS volume
	// It will create the PV with a ClaimRef so that no other PVCs will bind to it
	accessMode := []corev1.PersistentVolumeAccessMode{"ReadWriteMany"}
	volumeSize := "10Gi"
	namespace := namespaceName
	volumeSpec := &corev1.PersistentVolume{

		TypeMeta: metav1.TypeMeta{Kind: "PersistentVolume"},
		ObjectMeta: metav1.ObjectMeta{
			Name: volumeName,
		},

		Spec: corev1.PersistentVolumeSpec{

			AccessModes: accessMode,
			Capacity: corev1.ResourceList{
				corev1.ResourceName(corev1.ResourceStorage): resource.MustParse(volumeSize),
			},
			PersistentVolumeSource: v1.PersistentVolumeSource{
				NFS: &corev1.NFSVolumeSource{
					Path:   nfsPath,
					Server: nfsServer,
				},
			},
			ClaimRef: &corev1.ObjectReference{
				Name:      claimName,
				Namespace: namespace,
			},
		},
	}

	// get the persistent volumes
	_, getPVError := client.CoreV1().PersistentVolumes().Get(context.TODO(), volumeName, metav1.GetOptions{})

	if getPVError != nil {
		if debug {
			fmt.Printf("%s %s\n", debug_header, getPVError)
		}
		fmt.Println("No existing Persistent Volume found, creating a new one...")
		_, createPVError := client.CoreV1().PersistentVolumes().Create(context.TODO(), volumeSpec, metav1.CreateOptions{})
		if createPVError != nil {
			fmt.Println("Failed to create Persistent Volume...")
			panic(createPVError)
		}
		return
	}
	// We want to only update the PersistentVolume if the Claim is unbound or in another state
	// If the claim is already bound, don't touch the PV
	claimOutput, _ := client.CoreV1().PersistentVolumeClaims(namespaceName).Get(context.TODO(), claimName, metav1.GetOptions{})
	if claimOutput.Status.Phase == "Bound" {
		fmt.Printf("%s PVC is already bound to the PV... No action taken\n", debug_header)
		return
	}
	// Because OCP adds resource versions and uuid, if the PVC gets deleted for some reason, the PV will never become bound
	// Therefore we want to update the PV definition to remove UUID and resource version information
	_, updatePVError := client.CoreV1().PersistentVolumes().Update(context.TODO(), volumeSpec, metav1.UpdateOptions{})
	fmt.Printf("%s the PV has been updated with the new PVC\n", debug_header)
	if updatePVError != nil {
		fmt.Println("Failed to update Persistent Volume...")
		panic(updatePVError)
	}
}

func createPVCDefinition(namespaceName string, pvcName string, volumeName string, volumeSize string, accessMode []corev1.PersistentVolumeAccessMode) ([]corev1.PersistentVolumeAccessMode, *corev1.PersistentVolumeClaim) {
	// Return a different PVC Spec depending on whether or not a volumeName is passed in
	// The assumption is that a PVC without an explicite volume name is intended to be dynamic storage backed
	// The accessMode is also returned
	pvcSpec := &corev1.PersistentVolumeClaim{}
	if volumeName == "" {
		pvcSpec = &corev1.PersistentVolumeClaim{
			ObjectMeta: metav1.ObjectMeta{
				Name:      pvcName,
				Namespace: namespaceName,
				UID:       types.UID(pvcName),
			},
			Spec: corev1.PersistentVolumeClaimSpec{
				AccessModes: accessMode,
				Resources: corev1.ResourceRequirements{
					Requests: corev1.ResourceList{
						corev1.ResourceName(corev1.ResourceStorage): resource.MustParse(volumeSize),
					},
				},
			},
			Status: corev1.PersistentVolumeClaimStatus{
				Phase:       corev1.ClaimBound,
				AccessModes: accessMode,
				Capacity: corev1.ResourceList{
					corev1.ResourceName(corev1.ResourceStorage): resource.MustParse(volumeSize),
				},
			},
		}
		return accessMode, pvcSpec
	}
	accessMode = []corev1.PersistentVolumeAccessMode{corev1.ReadWriteMany}
	pvcSpec = &corev1.PersistentVolumeClaim{
		ObjectMeta: metav1.ObjectMeta{
			Name:      pvcName,
			Namespace: namespaceName,
			UID:       types.UID(pvcName),
		},
		Spec: corev1.PersistentVolumeClaimSpec{
			AccessModes: accessMode,
			Resources: corev1.ResourceRequirements{
				Requests: corev1.ResourceList{
					corev1.ResourceName(corev1.ResourceStorage): resource.MustParse(volumeSize),
				},
			},
			VolumeName: volumeName,
		},
		Status: corev1.PersistentVolumeClaimStatus{
			Phase:       corev1.ClaimBound,
			AccessModes: accessMode,
			Capacity: corev1.ResourceList{
				corev1.ResourceName(corev1.ResourceStorage): resource.MustParse(volumeSize),
			},
		},
	}
	return accessMode, pvcSpec
}

func createMissingPVCs(namespaceName string, nfsPVCName string, volumeName string, volumeSize string, debug bool, debug_header string, client *kubernetes.Clientset) {
	//This function will create a PVC if it doesn't exist already
	// Additionally, it will check to make sure that the PVC is not lost
	// if it is, the pvc will be deleted and recreated
	createPVC := false
	accessMode := []corev1.PersistentVolumeAccessMode{corev1.ReadWriteOnce}
	claimOutput, exist_err := client.CoreV1().PersistentVolumeClaims(namespaceName).Get(context.TODO(), nfsPVCName, metav1.GetOptions{})
	if claimOutput.Status.Phase == "Lost" {
		deletePVCError := client.CoreV1().PersistentVolumeClaims(namespaceName).Delete(context.TODO(), nfsPVCName, metav1.DeleteOptions{})
		i := 0
		// We want to wait up to 30 seconds for a terminating PVC to be removed
		for i <= 3 {
			claimOutput, _ := client.CoreV1().PersistentVolumeClaims(namespaceName).Get(context.TODO(), nfsPVCName, metav1.GetOptions{})
			if claimOutput.Status.Phase != "Terminating" {
				time.Sleep(10 * time.Second)
			}

			i++
		}
		if deletePVCError != nil {
			fmt.Println("The PVC was in a 'Lost' state but it could not be removed. Please investigate")
			panic(deletePVCError)
		}
	}

	// go get the PVC Sepc
	accessMode, pvcSpec := createPVCDefinition(namespaceName, nfsPVCName, volumeName, volumeSize, accessMode)
	if claimOutput.Status.AccessModes != nil {
		if claimOutput.Status.AccessModes[0] != accessMode[0] {
			if debug {
				fmt.Printf("%s Current Access Mode: %s\n 			Requested Access Mode: %s\n", debug_header, claimOutput.Status.AccessModes[0], accessMode[0])
				fmt.Printf("%s Volume Name: %s\n", debug_header, claimOutput.Spec.VolumeName)
			}
			fmt.Println("PVC already exists")
			fmt.Println("Access Mode of existing PVC does not match")
			fmt.Println("Exiting")
			os.Exit(1)

		}
	}
	// a "GET" error is not necessarily bad at first, it could mean this is the first time the job is run
	// Create the PVC if it doesn't exist
	if exist_err != nil || createPVC == true {
		if debug {
			fmt.Printf("%s Attempting to create the PVC: %s\n", debug_header, nfsPVCName)
		}
		_, createPVCError := client.CoreV1().PersistentVolumeClaims(namespaceName).Create(context.TODO(), pvcSpec, metav1.CreateOptions{})

		if createPVCError != nil {
			fmt.Println("Failed to create PVC")
			panic(createPVCError)
		}
		i := 0
		// Wait for up to 100 seconds for the PVC to become bound
		for i <= 10 {
			claimOutput, _ := client.CoreV1().PersistentVolumeClaims(namespaceName).Get(context.TODO(), nfsPVCName, metav1.GetOptions{})
			if claimOutput.Status.Phase != "Bound" {
				time.Sleep(10 * time.Second)
				timeElapsed := i * 10
				fmt.Printf("PVC is not yet bound after %d\n", timeElapsed)
			}
			if claimOutput.Status.Phase == "Bound" {
				return
			}
			i++
			// If we cannot bind to a PV, halt the program
			if i == 10 {
				panic("Problem binding PVC to a PV... exiting")
			}
		}
	}

}

func pullBackupLocal(nodeName string, localBackupDirectory string, namespaceName string, jobName string, debug bool, debug_header string, kubeconfig string, ocpBinaryPath string, client *kubernetes.Clientset) {
	// There may be times where you cannot attach or do not want to attach a PVC
	// in this case you want to pull the backup locally

	// tarball should be in our temporary location on the control plane host
	tempTarball := "/host/tmp/etcd_backup.tar.gz"
	cmd := ""
	//tempBackupDir := "/host/tmp/assests"
	if ocpBinaryPath == "" {
		cmd = fmt.Sprintf("KUBECONFIG=%s oc debug node/%s", kubeconfig, nodeName)
	} else {
		cmd = fmt.Sprintf("KUBECONFIG=%s %s/oc debug node/%s", kubeconfig, ocpBinaryPath, nodeName)
	}

	catCMD := cmd + " -- cat " + tempTarball
	todayDate := fmt.Sprintf("%d-%d-%d_%d_%d_%d", time.Now().Year(), time.Now().Month(), time.Now().Day(), time.Now().Hour(), time.Now().Minute(), time.Now().Second())
	localTarballLocation := localBackupDirectory + "/etcd_backup_" + todayDate + ".db.tgz"
	// this is a hack to get around the error "arguments in resource/name form may not have more than one slash"
	// seems to be some weird escaping happening in the exec command
	// perhaps a better way would be to try and create a debug node pod
	fmt.Println("Attempint to copy tarball locally...")
	if debug {
		fmt.Printf("%s running the following command \n\t\t\t%s\n", debug_header, catCMD)
	}
	output, catTarballError := exec.Command("sh", "-c", catCMD).Output()
	if catTarballError != nil {
		fmt.Println("Failed to read remote file")
		log.Fatal(catTarballError)
	}
	// The output is captured as a byte[] so we want to write this out to a file
	f, createLocalFileError := os.Create(localTarballLocation)

	if createLocalFileError != nil {
		fmt.Println("Failed to create local file")
		log.Fatal(createLocalFileError)
	}

	defer f.Close()

	_, saveFileError := f.Write(output)

	if saveFileError != nil {
		fmt.Println("Failed to save local file")
		log.Fatal(saveFileError)
	}

	fmt.Println("Starting cleanup")
	cleanupCMD := cmd + " -- rm -fv " + tempTarball
	if debug {
		fmt.Printf("%s using the following cleanup command:\n\t\t\t  %s\n", debug_header, cleanupCMD)
	}
	out2, _ := exec.Command("sh", "-c", cleanupCMD).CombinedOutput()

	fmt.Println(string(out2))
	return
}

func waitForJobComplete(namespaceName string, jobName string, debug bool, debug_header string, nodeName string, client *kubernetes.Clientset) bool {
	// We want to wait for the backup job to actually complete before we attempt to copy the tarball locally
	i := 0
	success := false
	for i <= 24 {
		job, getJobError := client.BatchV1().Jobs(namespaceName).Get(context.TODO(), jobName, metav1.GetOptions{})
		if getJobError != nil {
			fmt.Println("Error getting Job... Might not exist?")
			panic(getJobError)
		}

		if job.Status.Active == 0 && job.Status.Succeeded == 0 && job.Status.Failed == 0 {
			fmt.Printf("%s hasn't started yet\n", job.Name)
		}

		if job.Status.Active > 0 {
			fmt.Printf("%s is still running after %d seconds\n", job.Name, i*10)
		}
		if job.Status.Succeeded > 0 {
			success = true
			time.Sleep(10 * time.Second)
			break
		}
		if job.Status.Failed > 0 {
			success = false
		}

		if i > 5 {
			fmt.Println()
		}
		time.Sleep(10 * time.Second)
		i++
	}
	if success == false {
		fmt.Printf("Job did not complete after 240 seconds, something __may__ be wrong. Tarball **MAY** exist on debug node %s but not on localhost", nodeName)
	}
	return success
}

func main() {
	backupPodImage := flag.String("backup-pod-image-version", "v4.9", "The version of the ose-client to use")
	kubeConfigFile := flag.String("kube-config", "", "Full path to kubeconfig")
	usePVC := flag.Bool("use-pvc", true, "Does the backup pod use a PVC? If not, dump it backup to local directory")
	localBackupDirectory := flag.String("local-backup-dir", "/tmp", "Full LOCAL path to put backup")
	etcdBackupProject := flag.String("etcd-backup-project", "ocp-etcd-backup", "Which project to create etcd backup pods")
	nfsServer := flag.String("nfs-server", "", "IP or Hostname of the NFS Server")
	nfsPath := flag.String("nfs-path", "", "NFS Path to save backups to")
	debug := flag.Bool("debug", false, "Turns on some debug messages")
	taintName := flag.String("taint", "node-role.kubernetes.io/master", "Specify a taint to ignore so the pod can run on the control plane")
	useNFS := flag.Bool("use-nfs", false, "Denotes whether the PVC uses NFS or not")
	nfsPVName := flag.String("nfs-volume-name", "etcd-nfs-backup-vol", "NFS Path to save backups to")
	nfsPVCName := flag.String("nfs-claim-name", "", "NFS PVC claim name which binds to a persistent volume")
	dynamicPVCName := flag.String("dynamic-claim-name", "", "Name of the dynamic PVC")
	useDynamicStorage := flag.Bool("use-dynamic-storage", false, "Create a PVC for dynamic storage")
	ocpBinaryPath := flag.String("oc-binary-path", "", "Path to the OC cli binary")
	flag.Parse()
	imageURL := "registry.redhat.io/openshift4/ose-cli:" + *backupPodImage
	backupProject := *etcdBackupProject
	pvcSize := "5Gi"
	serviceAccountName := "openshift-backup"
	randomUUID := randomString(4)
	jobName := "etcd-backup-" + randomUUID
	debug_header := "    (DEBUG)    --->    "

	// do error checking based on if PVCs are being used and if so, which type
	if *usePVC {
		if *useNFS {
			if *nfsServer == "" {
				flag.Usage()
				fmt.Println("")
				fmt.Println("!!! NFS Server is required if using a PVC !!!")
				os.Exit(1)
			}
			if *nfsPath == "" {
				flag.Usage()
				fmt.Println("")
				fmt.Println("!!! NFS Path is required if using a PVC !!!")
				os.Exit(1)

			}

			if *nfsPVCName == "" {
				*nfsPVCName = "etcd-nfs-backup-claim"
				if *debug {
					fmt.Printf("%s No Claim name speicified!\n", debug_header)
					fmt.Printf("%s Using: %s\n", debug_header, *nfsPVCName)

				}
				if *debug {
					fmt.Printf("%s Using: %s\n", debug_header, *nfsPVCName)

				}
			}
		}
		if *useDynamicStorage {
			if *dynamicPVCName == "" {
				*dynamicPVCName = "etcd-dynamic-backup-claim"
				if *debug {
					fmt.Printf("%s No Claim name speicified!\n", debug_header)
					fmt.Printf("%s Using: %s\n", debug_header, *dynamicPVCName)
				}
			}
			if *debug {
				fmt.Printf("%s Using: %s\n", debug_header, *dynamicPVCName)
			}
		}
	}

	// This is a temporary holder until I find a better way to pass in this config
	// If no kubeconfig is passed in, attempt to find it in a default location
	if *kubeConfigFile == "" {
		fmt.Println("No kubeconfig attempting to use ~/.kube/auth/kubeconfig")
		userName, _ := user.Current()
		kubePath := fmt.Sprintf("/home/%s/.kube/auth/kubeconfig", userName)
		if _, err := os.Stat(kubePath); errors.Is(err, os.ErrNotExist) {
			panic("Kubeconfig was not passed in and does not exist in the default location... cannot continue!")
		}
		*kubeConfigFile = "${USER}/.kube/auth/kubeconfig"
	}

	fmt.Println("Connecting to cluster")
	if *debug {
		fmt.Printf("%s Connecting using kubeconfig: %s\n", debug_header, *kubeConfigFile)
	}
	config, err := clientcmd.BuildConfigFromFlags("", *kubeConfigFile)

	if err != nil {
		panic(err)
	}

	client, _ := kubernetes.NewForConfig(config)
	fmt.Println("Attempting to find nodes with the label: node-role.kubernetes.io/master=")
	nodes, err := client.CoreV1().Nodes().List(context.TODO(), metav1.ListOptions{LabelSelector: "node-role.kubernetes.io/master="})

	if err != nil {
		fmt.Println(err)
		return
	}

	// It should be safe to assume that at least 1 item exists since the above error should have exited the program
	// if no results were found
	debug_node := nodes.Items[0].Name
	if *debug {
		fmt.Printf("%s using node: %s\n", debug_header, debug_node)
	}
	// Make sure the backup area exists
	if *debug {
		fmt.Printf("%s attempting to use project: %s\n", debug_header, backupProject)
		fmt.Printf("%s Project will be created if it doesn't exist\n", debug_header)
	}
	createProject(backupProject, serviceAccountName, *debug, debug_header, client)

	// make sure the PV exists
	backupJob := createBackupPodNoPVC(debug_node, backupProject, imageURL, jobName, serviceAccountName, *taintName, *debug, debug_header, *ocpBinaryPath)
	if *usePVC {
		// make sure the pv exists
		if *useNFS {
			fmt.Println("Checking to see if we need to create PV")
			createPersistentNFSVolume(backupProject, *nfsServer, *nfsPath, *debug, debug_header, *nfsPVName, *nfsPVCName, client)
		}
		// make sure the pvc exists
		fmt.Println("Checking to see if we need to create PVC")
		if *useNFS {
			if *debug {
				fmt.Printf("%s Creating NFS PVC\n", debug_header)
			}
			createMissingPVCs(backupProject, *nfsPVCName, *nfsPVName, pvcSize, *debug, debug_header, client)
		}
		if *useDynamicStorage {
			if *debug {
				fmt.Printf("%s Creating Dynamic Storage PVC\n", debug_header)
			}
			createMissingPVCs(backupProject, *dynamicPVCName, "", pvcSize, *debug, debug_header, client)
		}
		fmt.Println("Creating the backup job")
		if *debug {
			if *useNFS {
				fmt.Printf("%s Job: %s\n 			Project: %s \n 			Node: %s\n			PVC: %s\n", debug_header, jobName, backupProject, debug_node, *nfsPVCName)
			}
		}
		backupJob = createBackupPodWithPVC(debug_node, backupProject, imageURL, *nfsPVCName, *dynamicPVCName, jobName, serviceAccountName, *taintName, *debug, debug_header, *ocpBinaryPath)
	}

	_, backupJobError := client.BatchV1().Jobs(backupProject).Create(context.TODO(), backupJob, metav1.CreateOptions{})

	if backupJobError != nil {
		fmt.Println("!!! Failed to create backup job...")
		panic(backupJobError)
	}
	success := waitForJobComplete(backupProject, jobName, *debug, debug_header, debug_node, client)
	if success {
		if *usePVC == false {
			fmt.Println("Starting to pull backup locally")
			pullBackupLocal(debug_node, *localBackupDirectory, backupProject, jobName, *debug, debug_header, *kubeConfigFile, *ocpBinaryPath, client)
		}
		fmt.Println("Backup job complete")
	}
}
