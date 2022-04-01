package main

import (
	"context"
	"flag"
	"fmt"
	"log"
	"math/rand"
	"os"
	"os/exec"
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

func createProject(namespaceName string, serviceAccountName string, client *kubernetes.Clientset) {
	//Check to see if project exists
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

	if exist_err != nil {
		_, err := client.CoreV1().Namespaces().Create(context.TODO(), namespace, metav1.CreateOptions{})

		if err != nil {
			panic(err)
		}
	}
	fmt.Println("Creating service account...")
	createServiceAccount(namespaceName, serviceAccountName, client)
	fmt.Println("Ensuring that ClusterRole exists...")
	createClusterPriviligedRole(namespaceName, client)
	createClusterBackupRole(namespaceName, client)

	fmt.Println("Checking to make sure ClusterRole is applied to 'default' service account...")
	createClusterPriviligedRoleBinding(namespaceName, serviceAccountName, client)
	createClusterBackupRoleBinding(namespaceName, serviceAccountName, client)

}

func createBackupPodNoPVC(nodeName string, projectName string, imageURL string, jobName string, serviceAccountName string) *batchv1.Job {
	// Creates a debug pod from the nodeName passed in
	// Pod is based on the ose-cli pod and runs an etcd backup
	// in the future may take namespace and other arguments to make this more flexible
	// this command should be run as a prefix to all commands in the debug pod
	cmd := "oc debug node/" + nodeName + " -- chroot /host"
	// create a temporary tarball which will eventually be moved to the pod's PVC
	tempTarball := "/tmp/etcd_backup.tar.gz"
	tempBackupDir := "/tmp/assets/backup"
	cleanupCMD := cmd + " rm -rfv " + tempBackupDir
	backupCMD := cmd + " /usr/local/bin/cluster-backup.sh " + tempBackupDir
	tarCMD := cmd + " tar czf " + tempTarball + " " + tempBackupDir
	// using cat to stream the tarball from one host to another is one way to transfer without mounting
	// any mounts on the debug host
	jobSpec := &batchv1.Job{
		ObjectMeta: metav1.ObjectMeta{
			Name:      jobName,
			Namespace: projectName,
		},
		Spec: batchv1.JobSpec{
			Template: corev1.PodTemplateSpec{
				Spec: corev1.PodSpec{
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

func createBackupPodWithPVC(nodeName string, projectName string, imageURL string, pvcName string, jobName string, serviceAccountName string) *batchv1.Job {
	// Creates a debug pod from the nodeName passed in
	// Pod is based on the ose-cli pod and runs an etcd backup
	// in the future may take namespace and other arguments to make this more flexible
	// this command should be run as a prefix to all commands in the debug pod
	cmd := "oc debug node/" + nodeName + " -- chroot /host"
	// create a temporary tarball which will eventually be moved to the pod's PVC
	tempTarball := "/tmp/etcd_backup.tar.gz"
	tempBackupDir := "/tmp/assets/backup"
	// generate a random UUID for the job name
	backupCMD := cmd + " /usr/local/bin/cluster-backup.sh " + tempBackupDir
	tarCMD := cmd + " tar czf " + tempTarball + " " + tempBackupDir
	test := true
	// using cat to stream the tarball from one host to another is one way to transfer without mounting
	// any mounts on the debug host
	moveTarballCMD := cmd + " cat " + tempTarball + " > /backups/backup_$(date +%Y-%m-%d_%H-%M_%Z).db.tgz"
	cleanupCMD := cmd + " rm -rfv " + tempBackupDir + " && " + cmd + " rm -f " + tempTarball
	jobSpec := &batchv1.Job{
		ObjectMeta: metav1.ObjectMeta{
			Name:      jobName,
			Namespace: projectName,
		},
		Spec: batchv1.JobSpec{
			Template: corev1.PodTemplateSpec{
				Spec: corev1.PodSpec{
					Containers: []corev1.Container{
						{
							Name:            jobName,
							Image:           imageURL,
							ImagePullPolicy: corev1.PullIfNotPresent,
							Command: []string{
								"/bin/bash",
								"-c",
								backupCMD + " && " + tarCMD + " && " + moveTarballCMD + " && " + cleanupCMD,
							},
							VolumeMounts: []corev1.VolumeMount{
								corev1.VolumeMount{
									Name:      "etcd-backup-mount",
									MountPath: "/backups",
								},
							},
							SecurityContext: &corev1.SecurityContext{
								Privileged: &test,
							},
						},
					},
					RestartPolicy:      corev1.RestartPolicyNever,
					ServiceAccountName: serviceAccountName,
					Volumes: []corev1.Volume{
						{
							Name: "etcd-backup-mount",
							VolumeSource: corev1.VolumeSource{
								PersistentVolumeClaim: &corev1.PersistentVolumeClaimVolumeSource{
									ClaimName: pvcName,
								},
							},
						},
					},

					NodeSelector: map[string]string{
						"node-role.kubernetes.io/master": "",
					},
				},
			},
		},
	}

	return (jobSpec)
}

func createPersistentVolume(namespaceName string, client *kubernetes.Clientset) {
	//
	accessMode := []corev1.PersistentVolumeAccessMode{"ReadWriteMany"}
	volumeName := "etcd-backup"
	volumeSize := "10Gi"
	path := "/storage/vms/origin_nfs/etcd_backups"
	serverAddress := "192.168.99.95"
	//accessMode = "ReadWriteMany"
	claimName := "etcd-backup-pvc"
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
					Path:   path,
					Server: serverAddress,
				},
			},
			ClaimRef: &corev1.ObjectReference{
				Name:      claimName,
				Namespace: namespace,
			},
		},
	}

	_, err := client.CoreV1().PersistentVolumes().Update(context.TODO(), volumeSpec, metav1.UpdateOptions{})

	if err != nil {
		panic(err)
	}
}

func createMissingPVCs(namespaceName string, pvcName string, volumeName, volumeSize string, client *kubernetes.Clientset) {
	//

	pvcSpec := &corev1.PersistentVolumeClaim{
		ObjectMeta: metav1.ObjectMeta{
			Name:      pvcName,
			Namespace: namespaceName,
			UID:       types.UID(pvcName),
		},
		Spec: corev1.PersistentVolumeClaimSpec{
			AccessModes: []corev1.PersistentVolumeAccessMode{corev1.ReadWriteMany},
			Resources: corev1.ResourceRequirements{
				Requests: corev1.ResourceList{
					corev1.ResourceName(corev1.ResourceStorage): resource.MustParse(volumeSize),
				},
			},
			VolumeName: volumeName,
			//VolumeMode: &v1.PersistentVolumeFilesystem,
		},
		Status: corev1.PersistentVolumeClaimStatus{
			Phase:       corev1.ClaimBound,
			AccessModes: []corev1.PersistentVolumeAccessMode{corev1.ReadWriteMany},
			Capacity: corev1.ResourceList{
				corev1.ResourceName(corev1.ResourceStorage): resource.MustParse(volumeSize),
			},
		},
	}
	_, exist_err := client.CoreV1().PersistentVolumeClaims(namespaceName).Get(context.TODO(), pvcName, metav1.GetOptions{})

	if exist_err != nil {
		_, err := client.CoreV1().PersistentVolumeClaims(namespaceName).Create(context.TODO(), pvcSpec, metav1.CreateOptions{})

		if err != nil {
			panic(err)
		}
	}

}

func pullBackupLocal(nodeName string, localBackupDirectory string, namespaceName string, jobName string, debug bool, debug_header string, client *kubernetes.Clientset) {
	// There may be times where you cannot attach or do not want to attach a PVC
	// in this case you want to pull the backup locally
	i := 0
	success := false

	// We want to wait for the backup job to actually complete before we attempt to copy the tarball locally
	for i <= 24 {
		job, err := client.BatchV1().Jobs(namespaceName).Get(context.TODO(), jobName, metav1.GetOptions{})

		if err != nil {
			panic(err)
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
		time.Sleep(10 * time.Second)
		i++
	}
	if success {
		// tarball should be in our temporary location on the control plane host
		tempTarball := "/host/tmp/etcd_backup.tar.gz"
		//tempBackupDir := "/host/tmp/assests"
		cmd := "oc debug node/" + nodeName
		catCMD := cmd + " -- cat " + tempTarball
		todayDate := fmt.Sprintf("%d-%d-%d_%d_%d_%d", time.Now().Year(), time.Now().Month(), time.Now().Day(), time.Now().Hour(), time.Now().Minute(), time.Now().Second())
		localTarballLocation := localBackupDirectory + "/etcd_backup_" + todayDate + ".db.tgz"
		// this is a hack to get around the error "arguments in resource/name form may not have more than one slash"
		// seems to be some weird escaping happening in the exec command
		// perhaps a better way would be to try and create a debug node pod
		fmt.Println("Attempint to copy tarball locally...")
		if debug != false {
			fmt.Printf("%s running the following command \n\t\t\t  %s", debug_header, catCMD)
		}
		output, err := exec.Command("sh", "-c", catCMD).Output()
		if err != nil {
			log.Fatal(err)
		}
		// The output is captured as a byte[] so we want to write this out to a file
		f, err2 := os.Create(localTarballLocation)

		if err2 != nil {
			log.Fatal(err2)
		}

		defer f.Close()

		_, err3 := f.Write(output)

		if err3 != nil {
			log.Fatal(err3)
		}

		fmt.Println("Starting cleanup")
		cleanupCMD := cmd + " -- rm -fv " + tempTarball
		if debug != false {
			fmt.Printf("%s using the following cleanup command:\n\t\t\t  %s\n", debug_header, cleanupCMD)
		}
		out2, _ := exec.Command("sh", "-c", cleanupCMD).CombinedOutput()

		fmt.Println(string(out2))
		return
	}
	fmt.Printf("Job did not complete after 240 seconds, something may be wrong. Tarball may exist on debug node %s but not on localhost", nodeName)
}

func main() {
	backupPodImage := flag.String("backup-pod-image-version", "v4.8", "The version of the ose-client to use")
	kubeConfigFile := flag.String("kube-config", "", "Full path to kubeconfig")
	usePVC := flag.Bool("use-pvc", true, "Does the backup pod use a PVC? If not, dump it backup to local directory")
	localBackupDirectory := flag.String("local-backup-dir", "/tmp", "Full LOCAL path to put backup")
	etcdBackupProject := flag.String("etcd-backup-project", "ocp-etcd-backup", "Which project to create etcd backup pods")
	debug := flag.Bool("debug", false, "Turns on some debug messages")
	flag.Parse()
	imageURL := "registry.redhat.io/openshift4/ose-cli:" + *backupPodImage
	backupProject := *etcdBackupProject
	pvcName := "etcd-backup-pvc"
	pvcSize := "1Gi"
	pvName := "etcd-backup"
	serviceAccountName := "openshift-backup"
	randomUUID := randomString(4)
	jobName := "etcd-backup-" + randomUUID
	debug_header := "    (DEBUG)    --->    "
	if *debug != false {
		// This is an empty place holder until I decide how i want to implement the debug flag
	}

	// This is a temporary holder until I find a better way to pass in this config
	// If no kubeconfig is passed in, attempt to find it in a default location
	if *kubeConfigFile == "" {
		*kubeConfigFile = "${USER}/.kube/auth/kubeconfig"
		fmt.Println("No kubeconfig attempting to use ~/.kube/auth/kubeconfig")
	}
	fmt.Println("Connecting to cluster")
	if *debug != false {
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
	if *debug != false {
		fmt.Printf("%s using node: %s\n", debug_header, debug_node)
	}
	// Make sure the backup area exists
	if *debug != false {
		fmt.Printf("%s attempting to use project: %s\n", debug_header, backupProject)
		fmt.Println("Project will be created if it doesn't exist")
	}
	createProject(backupProject, serviceAccountName, client)

	// make sure the PV exists
	//createPersistentVolume(volumeInfo, client)
	backupJob := createBackupPodNoPVC(debug_node, backupProject, imageURL, jobName, serviceAccountName)
	if *usePVC != false {
		// make sure the pv exists
		fmt.Println("Creating the Volume")
		createPersistentVolume(backupProject, client)
		// make sure the pvc exists
		fmt.Println("Creating the PVC")
		createMissingPVCs(backupProject, pvcName, pvName, pvcSize, client)
		fmt.Println("Creating the backup job")
		if *debug != false {
			fmt.Printf("%s Job: %s\n 			Project: %s \n 			Node: %s\n			PVC: %s\n", debug_header, jobName, backupProject, debug_node, pvcName)
		}
		backupJob = createBackupPodWithPVC(debug_node, backupProject, imageURL, pvcName, jobName, serviceAccountName)
	}

	_, err1 := client.BatchV1().Jobs(backupProject).Create(context.TODO(), backupJob, metav1.CreateOptions{})
	if *usePVC == false {
		fmt.Println("Starting to pull backup locally")
		pullBackupLocal(debug_node, *localBackupDirectory, backupProject, jobName, *debug, debug_header, client)
	}

	if err1 != nil {
		panic(err1)
	}

}
