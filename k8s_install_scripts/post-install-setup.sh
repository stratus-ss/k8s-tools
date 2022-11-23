#!/bin/bash
# This script is related to a single node installation of vanilla k8s
# It is meant to be run after the kubeadm --init has been run

# remove the taint preventing scheduling on the node 
kubectl taint nodes --all node-role.kubernetes.io/control-plane-


wget https://raw.githubusercontent.com/kubeovn/kube-ovn/release-1.10/dist/images/install.sh
mv install.sh ovn-install.sh
sh ovn-install.sh

cat <<EOF | sudo tee haproxy-ingress-values.yaml
controller:
  hostNetwork: true
EOF


curl -fsSL -o get_helm.sh https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3
sh get_helm.sh
helm repo add haproxy-ingress https://haproxy-ingress.github.io/charts
helm repo update
helm install haproxy-ingress haproxy-ingress/haproxy-ingress  --create-namespace --namespace ingress-controller  --version 0.13.9  -f haproxy-ingress-values.yaml

sleep 60

helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
kubectl create ns prom
helm install --namespace prom prom-stack prometheus-community/kube-prometheus-stack

kubectl --namespace prom create ingress grafana\
  --annotation kubernetes.io/ingress.class=haproxy\
  --rule="grafana.k3s.lab/*=prom-stack-grafana:80,tls"


kubectl --namespace prom create ingress alertmanager\
  --annotation kubernetes.io/ingress.class=haproxy\
  --rule="alerts.k3s.lab/*=prom-stack-kube-prometheus-alertmanager:9093,tls"


kubectl --namespace prom create ingress prom-k8s\
  --annotation kubernetes.io/ingress.class=haproxy\
  --rule="prom-k8s.k3s.lab/*=prom-stack-kube-prometheus-prometheus:9090,tls"
