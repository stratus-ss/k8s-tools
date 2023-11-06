package main

import (
	"context"
	"fmt"
	"os"
	"time"

	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/resource"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/client-go/kubernetes"
)

func createPVCDefinition(namespaceName string, pvcName string, volumeName string, volumeSize string, accessMode []corev1.PersistentVolumeAccessMode) ([]corev1.PersistentVolumeAccessMode, *corev1.PersistentVolumeClaim) {
	// Create a PersistentVolumeClaim definition based on the given parameters.
	//
	// Args:
	//     namespaceName: The name of the Kubernetes namespace where the PVC will be created.
	//     pvcName: The name of the PVC.
	//     volumeName: The name of the PersistentVolume that the PVC will be bound to. If empty, a dynamic PV will be created.
	//     volumeSize: The size of the PersistentVolume that the PVC will be bound to.
	//     accessMode: The access mode of the PVC.
	//
	// Returns:
	//     A tuple containing the access mode and the PersistentVolumeClaim object.
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

func createMissingPVCs(namespaceName string, nfsPVCName string, volumeName string, volumeSize string, debug bool, debugHeader string, client *kubernetes.Clientset) {
	// createMissingPVCs creates a PVC if it doesn't exist already and checks to make sure it isn't lost.
	// If the PVC is lost, it will be deleted and recreated.
	// Args:
	//     namespaceName: the name of the Kubernetes namespace where the PVC should be created
	//     nfsPVCName: the name of the NFS PVC to create or retrieve
	//     volumeName: the name of the volume to use for the PVC
	//     volumeSize: the size of the volume to use for the PVC
	//     debug: whether or not to enable debug logging
	//     debugHeader: a header to use when printing debug messages
	//     client: a Kubernetes clientset to use for interacting with the cluster

	createPVC := false
	accessMode := []corev1.PersistentVolumeAccessMode{corev1.ReadWriteOnce}

	// Check if the PVC already exists
	claimOutput, existErr := client.CoreV1().PersistentVolumeClaims(namespaceName).Get(context.TODO(), nfsPVCName, metav1.GetOptions{})
	if claimOutput.Status.Phase == "Lost" {
		// If the PVC is lost, delete it and recreate it
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

	// Get the PVC spec
	accessMode, pvcSpec := createPVCDefinition(namespaceName, nfsPVCName, volumeName, volumeSize, accessMode)

	// Check if the PVC already exists and has the correct access mode
	if claimOutput.Status.AccessModes != nil {
		if claimOutput.Status.AccessModes[0] != accessMode[0] {
			if debug {
				fmt.Printf("%s Current Access Mode: %s\n                        Requested Access Mode: %s\n", debugHeader, claimOutput.Status.AccessModes[0], accessMode[0])
				fmt.Printf("%s Volume Name: %s\n", debugHeader, claimOutput.Spec.VolumeName)
			}
			fmt.Println("PVC already exists")
			fmt.Println("Access Mode of existing PVC does not match")
			fmt.Println("Exiting")
			os.Exit(1)

		}
	}
	// a "GET" error is not necessarily bad at first, it could mean this is the first time the job is run
	// Create the PVC if it doesn't exist
	if existErr != nil || createPVC == true {
		if debug {
			fmt.Printf("%s Attempting to create the PVC: %s\n", debugHeader, nfsPVCName)
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
