package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"strings"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/tools/clientcmd"
)

// This program will crawl the projects in a cluster and retrieve any secrets
// which have the a specified username inside them (generally a pull secret)
// this can be very slow as it introspects all of the secrets in the cluster

func main() {
	// Get the command line arguments from the user
	serviceAccountName := flag.String("service-account", "deployer", "The name of the service account to find.")
	kubeConfigFile := flag.String("kube-config", "", "Full path to kubeconfig")
	flag.Parse()

	// If no kubeconfig is passed in, attempt to find it in a default location
	if *kubeConfigFile == "" {
		*kubeConfigFile = "${USER}/.kube/auth/kubeconfig"
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
		all_secrets, _ := client.CoreV1().Secrets(projectInfo.Name).List(context.TODO(), metav1.ListOptions{})
		for _, secretsInfo := range all_secrets.Items {
			if projectInfo.Name != "default" {
				individual_secret, _ := client.CoreV1().Secrets(projectInfo.Name).Get(context.TODO(), secretsInfo.Name, metav1.GetOptions{})
				for secretsKey, secretValue := range individual_secret.Data {
					if strings.Contains(secretsKey, "dockerconfigjson") {
						var result map[string]interface{}
						json.Unmarshal([]byte(secretValue), &result)
						// json structure {"auths":{"<repo>":{"username":"faker","password":"snoogy","email":"admin@me.com","auth":"ZmF2d5"}}}
						auths := result["auths"].(map[string]interface{})
						for _, val := range auths {
							unknownRepo := val.(map[string]interface{})
							var foundUsername string
							var password string
							for authHeadings, authValues := range unknownRepo {
								if strings.Contains(authHeadings, "username") {
									unknwonUsername := fmt.Sprintf("%v", authValues)
									if unknwonUsername == *serviceAccountName {
										foundUsername = unknwonUsername
									}
								}
								if strings.Contains(authHeadings, "password") {
									password = fmt.Sprintf("%v", authValues)
								}
							}
							fmt.Printf("Project Name: %s \n   Secret Name: %s \n   Username: %s \n   Password %s\n\n", projectInfo.Name, secretsInfo.Name, foundUsername, password)

						}
					}

				}
			}
		}

	}
}
