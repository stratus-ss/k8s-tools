package main

import (
	"context"

	corev1 "k8s.io/api/core/v1"
	rbac "k8s.io/api/rbac/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
)

func createClusterBackupRole(namespaceName string, client *kubernetes.Clientset) {
	// createClusterBackupRole creates a ClusterRole for etcd backup in the specified namespace
	// Args:
	//     namespaceName: The name of the namespace where the ClusterRole will be created
	//     client: A Kubernetes clientset used to interact with the Kubernetes API
	// Define the name and verbs for the ClusterRole

	roleName := "cluster-etcd-backup"
	nodeVerbs := []string{"get", "list"}
	apiGroup := []string{""}
	nodeResources := []string{"nodes"}
	podVerbs := []string{"get", "list", "create", "delete", "watch"}
	podResources := []string{"pods", "pods/log"}

	// Define the rules for the ClusterRole
	rules := []rbac.PolicyRule{
		rbac.PolicyRule{
			Verbs:     nodeVerbs,
			APIGroups: apiGroup,
			Resources: nodeResources,
		},
		rbac.PolicyRule{
			Verbs:     podVerbs,
			APIGroups: apiGroup,
			Resources: podResources,
		},
	}

	// Create the ClusterRole
	clusterRole := &rbac.ClusterRole{
		ObjectMeta: metav1.ObjectMeta{
			Name: roleName,
		},
		Rules: rules,
	}

	// Update the ClusterRole in the Kubernetes API
	_, err := client.RbacV1().ClusterRoles().Update(context.TODO(), clusterRole, metav1.UpdateOptions{})

	if err != nil {
		panic(err)
	}

}

func createClusterPriviligedRole(namespaceName string, client *kubernetes.Clientset) {
	// Creates the system:openshift:scc:privileged ClusterRole, which allows use of the privileged security context constraint.
	// createClusterPrivilegedRole creates a ClusterRole with the given namespace name and client.
	// The ClusterRole will have the following privileges:
	// - Use the security context constraint named "privileged" in the "security.openshift.io" API group.
	// Args:
	//
	//	namespaceName: The name of the namespace for which the ClusterRole should be created.
	//	client: A Kubernetes client used to interact with the Kubernetes API.
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
	// Creates the etcd-backup-privileged ClusterRoleBinding, which binds the system:openshift:scc:privileged ClusterRole to the given service account.
	// createClusterPrivilegedRoleBinding creates a ClusterRoleBinding for the given service account in the specified namespace.
	// The ClusterRoleBinding grants the service account the "system:openshift:scc:privileged" ClusterRole.
	//
	// Args:
	//       namespaceName: The name of the namespace where the service account is located.
	//       serviceAccountName: The name of the service account to grant privileges to.
	//       client: A Kubernetes clientset used to interact with the Kubernetes API.
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

// Creates the cluster-etcd-backup ClusterRoleBinding, which binds the cluster-etcd-backup ClusterRole to the given service account.

func createClusterBackupRoleBinding(namespaceName string, serviceAccountName string, client *kubernetes.Clientset) {
	// createClusterBackupRoleBinding creates a ClusterRoleBinding for the given service account in the specified namespace.
	// The ClusterRoleBinding will give the service account the privileges to perform etcd backups.
	//
	// Args:
	//       namespaceName: The name of the namespace where the service account is located.
	//       serviceAccountName: The name of the service account to create the ClusterRoleBinding for.
	//       client: A Kubernetes clientset used to interact with the Kubernetes API.
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
	// createServiceAccount creates a new ServiceAccount in the specified namespace
	// with the given name. If the ServiceAccount already exists, it will not be created.
	// Args:
	//       namespaceName: The name of the namespace where the service account is located.
	//       serviceAccountName: The name of the service account to create the ClusterRoleBinding for.
	//       client: A Kubernetes clientset used to interact with the Kubernetes API.
	// Create a new ServiceAccount object with the specified name and namespace
	serviceAccount := &corev1.ServiceAccount{
		ObjectMeta: metav1.ObjectMeta{
			Name:      serviceAccountName,
			Namespace: namespaceName,
		},
	}

	// Check if the ServiceAccount already exists in the specified namespace
	_, exist_err := client.CoreV1().ServiceAccounts(namespaceName).Get(context.TODO(), serviceAccountName, metav1.GetOptions{})
	if exist_err != nil {
		// If the ServiceAccount doesn't exist, create it
		_, err := client.CoreV1().ServiceAccounts(namespaceName).Create(context.TODO(), serviceAccount, metav1.CreateOptions{})
		if err != nil {
			// If there was an error creating the ServiceAccount, panic
			panic(err)
		}
	}
}
