package main

import (
	"context"
	"fmt"

	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
)

// createProject creates a new Kubernetes project with the given name and service account name.
// It also checks if the project already exists and creates it if it doesn't.
func createProject(namespaceName string, serviceAccountName string, debug bool, debugHeader string, client *kubernetes.Clientset) {
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
	_, existErr := client.CoreV1().Namespaces().Get(context.TODO(), namespaceName, metav1.GetOptions{})

	if debug {
		fmt.Printf("%s project: %s did not exist\n", debugHeader, namespaceName)
		fmt.Printf("%s creating the project %s\n", debugHeader, namespaceName)
	}
	if existErr != nil {
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
