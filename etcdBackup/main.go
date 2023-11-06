package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"os"
	"os/user"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/tools/clientcmd"
)

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
