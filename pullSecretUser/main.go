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
	firstDataType := flag.String("first-data-type", "dockerconfigjson", "The heading of the in the 'data' section of the secret you wish to inspect")
	secondDataType := flag.String("second-data-type", "", "The heading of the in the 'data' section of the secret you wish to inspect")
	ignoreOpenShiftProjects := flag.Bool("ignore-openshift", true, "Ignores the Openshift-* projects to speed things up")
	debug := flag.Bool("debug", false, "Turns on some debug messages")
	flag.Parse()

	debugHeader := "\n(( DEBUG )) -->"

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
		// get all the secrets in the current namespace
		if *debug != false {
			fmt.Printf("%s Project is: %s", debugHeader, projectInfo.Name)
		}
		if *ignoreOpenShiftProjects == true && strings.Contains(projectInfo.Name, "openshift") {
			continue
		}
		all_secrets, _ := client.CoreV1().Secrets(projectInfo.Name).List(context.TODO(), metav1.ListOptions{})
		for _, secretsInfo := range all_secrets.Items {
			if *debug != false {
				fmt.Printf("%s      Secret is: %s", debugHeader, secretsInfo.Name)
			}
			individual_secret, _ := client.CoreV1().Secrets(projectInfo.Name).Get(context.TODO(), secretsInfo.Name, metav1.GetOptions{})

			for secretsKey, secretValue := range individual_secret.Data {
				if strings.Contains(secretsKey, *firstDataType) || strings.Contains(secretsKey, *secondDataType) {
					var result map[string]interface{}
					json.Unmarshal([]byte(secretValue), &result)
					// json structure {"auths":{"<repo>":{"username":"faker","password":"snoogy","email":"admin@me.com","auth":"ZmF2d5"}}}
					// Some maps may be empty, we want to ignore them as they wont have the keys we are looking for
					auths, ok := result["auths"].(map[string]interface{})

					if !ok {
						if *debug != false {
							fmt.Printf("%s   WARNING!!  %s   has unexpected format", debugHeader, secretsInfo.Name)
						}
					}

					for _, val := range auths {
						unknownRepo, ok := val.(map[string]interface{})
						if !ok {
							if *debug != false {
								fmt.Printf("%s   WARNING!!  %s   has unexpected format", debugHeader, secretsInfo.Name)
							}
						}
						var foundUsername string
						var password string
						for authHeadings, authValues := range unknownRepo {
							if strings.Contains(authHeadings, "username") {
								unknownUser := fmt.Sprintf("%v", authValues)
								if strings.ToLower(unknownUser) == strings.ToLower(*serviceAccountName) {
									foundUsername = unknownUser
								}
							}
							if strings.Contains(authHeadings, "password") {
								password = fmt.Sprintf("%v", authValues)
							}

						}
						if len(foundUsername) != 0 {
							fmt.Printf("\n\nSecret Name: %s \n   Project Name: %s \n   Username: %s \n   Password %s\n", secretsInfo.Name, projectInfo.Name, foundUsername, password)
						}

					}
				}
			}

		}
	}
}
