package main

import (
	"context"

	machinelearningv1 "github.com/seldonio/seldon-core/operator/apis/machinelearning.seldon.io/v1"
	seldonclientset "github.com/seldonio/seldon-core/operator/client/machinelearning.seldon.io/v1/clientset/versioned"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	_ "k8s.io/client-go/plugin/pkg/client/auth"
	"k8s.io/client-go/tools/clientcmd"
)

var clientset *seldonclientset.Clientset

func init() {
	clientset, _ = GetSeldonClientSet()
}

func GetSeldonClientSet() (*seldonclientset.Clientset, error) {
	config, err := clientcmd.BuildConfigFromFlags("", "")
	if err != nil {
		return nil, err
	}
	kubeClientset, err := seldonclientset.NewForConfig(config)
	if err != nil {
		return nil, err
	}
	return kubeClientset, nil
}

func ListSeldonDeployments(namespace string) (result *machinelearningv1.SeldonDeploymentList, err error) {
	return clientset.MachinelearningV1().SeldonDeployments(namespace).List(context.TODO(), metav1.ListOptions{})
}

func CreateSeldonDeployment(deployment *machinelearningv1.SeldonDeployment, namespace string) (sdep *machinelearningv1.SeldonDeployment, err error) {
	return clientset.MachinelearningV1().SeldonDeployments(namespace).Create(context.TODO(), deployment, metav1.CreateOptions{})
}
