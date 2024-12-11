#!/bin/bash

htpasswd -c htpasswd user1 password
oc create secret generic htpass-secret --from-file=htpasswd=./htpasswd -n openshift-config
oc apply -f ./htpasswd_cr.yaml
oc adm policy add-cluster-role-to-user cluster-admin user1
