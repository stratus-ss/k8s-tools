package main

import (
	"context"
	"fmt"
	"log"
	"math/rand"
	"os"
	"os/exec"
	"time"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
)

func pullBackupLocal(nodeName string, localBackupDirectory string, namespaceName string, jobName string, debug bool, debug_header string, kubeconfig string, ocpBinaryPath string, client *kubernetes.Clientset) {
	// pullBackupLocal copies a backup from a remote location to a local directory.
	// Args:
	// 		nodeName: the name of the node where the backup is located
	// 		localBackupDirectory: the path to the local directory where the backup should be copied
	// 		namespaceName: the name of the namespace where the backup is located
	// 		jobName: the name of the job that created the backup
	// 		debug: whether to enable debugging mode
	// 		debugHeader: the header to use for debugging messages
	// 		kubeconfig: the path to the Kubernetes configuration file
	// 		ocpBinaryPath: the path to the OpenShift binary
	// 		client: a pointer to the Kubernetes client
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
	// waitForJobComplete waits for the backup job to complete before attempting to copy the tarball locally.
	// Args:
	// 		namespaceName: the name of the namespace where the backup job is located
	// 		jobName: the name of the backup job
	// 		debug: whether to enable debugging mode
	// 		debugHeader: the header to use for debugging messages
	// 		nodeName: the name of the node where the backup job is running
	// 		client: a pointer to the Kubernetes client
	// It returns a boolean indicating whether the job completed successfully.
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

func randomString(length int) string {
	// Generate a random uuid to attach to the pod name
	// so that this can be called multiple times without conflicting with previous runs
	rand.Seed(time.Now().UnixNano())
	b := make([]byte, length)
	rand.Read(b)
	return fmt.Sprintf("%x", b)[:length]
}
