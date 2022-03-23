package main

import (
	"context"
	"flag"
	"fmt"
	"strings"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"

	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/tools/clientcmd"
)

// This program will crawl the projects in a cluster and retrieve any secrets
// which have the desired service account name
// This relies on the annotations in the service account in order to exclude
// Secrets that we don't care about

func main() {
	// Get the command line arguments from the user
	serviceAccountName := flag.String("service-account", "deployer", "The name of the service account to find.")
	kubeConfigFile := flag.String("kube-config", "", "Full path to kubeconfig")
	flag.Parse()

	// If no kubeconfig is passed in, attempt to find it in a default location
	if *kubeConfigFile == "" {
		*kubeConfigFile = "~/.kube/auth/kubeconfig"
		fmt.Println("No kubeconfig attempting to use ~/.kube/auth/kubeconfig")
	}
	config, err := clientcmd.BuildConfigFromFlags("", *kubeConfigFile)

	if err != nil {
		panic(err)
	}
	client, _ := kubernetes.NewForConfig(config)
	// get all the namespaces so that we can loop over the secrets in that project
	namespaces, _ := client.CoreV1().Namespaces().List(context.TODO(), metav1.ListOptions{})

	for _, projectInfo := range namespaces.Items {
		// Skip over the openshift projects by default
		if strings.Contains(projectInfo.Name, "openshift") {

		} else {
			all_secrets, _ := client.CoreV1().Secrets(projectInfo.Name).List(context.TODO(), metav1.ListOptions{})
			for _, secretsInfo := range all_secrets.Items {
				for key, serviceValue := range secretsInfo.Annotations {
					// If the line has both service-account annotation and contains the desired service account name
					// print out the information
					// because serviceAccountName is an argument, use a pointer to refer to it
					if strings.Contains(key, "service-account.name") && strings.Contains(serviceValue, *serviceAccountName) {
						fmt.Printf("Namespace: %s \n Secret: %s \n Account Name: %s \n", projectInfo.Name, secretsInfo.Name, *serviceAccountName)
					}
				}
			}
		}
	}
}
