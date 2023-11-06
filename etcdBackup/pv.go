package main

import (
	"context"
	"fmt"

	corev1 "k8s.io/api/core/v1"
	v1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/resource"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
)

func createPersistentNFSVolume(namespaceName string, nfsServer string, nfsPath string, debug bool, debugHeader string, volumeName string, claimName string, client *kubernetes.Clientset) {
	// createPersistentNFSVolume creates a PersistentVolume (PV) using the specified NFS server and path.
	// Args:
	// 		namespaceName: the name of the Kubernetes namespace where the PV will be created
	// 		nfsServer: the hostname or IP address of the NFS server
	// 		nfsPath: the path on the NFS server where the data will be stored
	// 		debug: a boolean indicating whether debug output should be printed
	// 		debugHeader: a string that will be prepended to each debug message
	// 		volumeName: the name of the PV
	// 		claimName: the name of the PersistentVolumeClaim (PVC) that will be used to bind the PV
	// 		client: a pointer to a kubernetes.Clientset object that will be used to interact with the Kubernetes API
	// This assumes the creation of an NFS volume
	// It will create the PV with a ClaimRef so that no other PVCs will bind to it
	accessMode := []corev1.PersistentVolumeAccessMode{"ReadWriteMany"}
	volumeSize := "10Gi"

	// Create the PV spec
	volumeSpec := &corev1.PersistentVolume{
		TypeMeta: metav1.TypeMeta{
			Kind: "PersistentVolume",
		},
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
				Namespace: namespaceName,
			},
		},
	}

	// Get the existing PV, if any
	_, getPVError := client.CoreV1().PersistentVolumes().Get(context.TODO(), volumeName, metav1.GetOptions{})

	if getPVError != nil {
		if debug {
			fmt.Printf("%s %s\n", debugHeader, getPVError)
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
		fmt.Printf("%s PVC is already bound to the PV... No action taken\n", debugHeader)
		return
	}
	// Because OCP adds resource versions and uuid, if the PVC gets deleted for some reason, the PV will never become bound
	// Therefore we want to update the PV definition to remove UUID and resource version information
	_, updatePVError := client.CoreV1().PersistentVolumes().Update(context.TODO(), volumeSpec, metav1.UpdateOptions{})
	fmt.Printf("%s the PV has been updated with the new PVC\n", debugHeader)
	if updatePVError != nil {
		fmt.Println("Failed to update Persistent Volume...")
		panic(updatePVError)
	}
}
