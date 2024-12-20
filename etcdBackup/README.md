## Purpose

The etcdBackup is meant to assist with a one-off etcd on-demand backup of the build in OpenShift ETCD database. There are four functions currently:
* Create the backup on a PVC backed by NFS
* Create the backup on a PVC backed by dynamic storage
* Create the backup on both NFS and dynamic storage volumes
* Create the backup and pull it to the local machine at a directory indicated

In addition, there is error handling for when PVCs get in an unbound state as well as waiting for the job to be completed

This program assumes that you have a kubeconfig file and that whichever user is used in the file has cluster-admin privilege in order to be able to create the appropriate resources

## Usage

```
Usage:
  -backup-pod-image-version string
    	The version of the ose-client to use (default "v4.9")
  -debug
    	Turns on some debug messages
  -dynamic-claim-name string
    	Name of the dynamic PVC
  -etcd-backup-project string
    	Which project to create etcd backup pods (default "ocp-etcd-backup")
  -kube-config string
    	Full path to kubeconfig
  -local-backup-dir string
    	Full LOCAL path to put backup (default "/tmp")
  -nfs-claim-name string
    	NFS PVC claim name which binds to a persistent volume
  -nfs-path string
    	NFS Path to save backups to
  -nfs-server string
    	IP or Hostname of the NFS Server
  -nfs-volume-name string
    	NFS Path to save backups to (default "etcd-nfs-backup-vol")
  -oc-binary-path string
    	Path to the OC cli binary
  -taint string
    	Specify a taint to ignore so the pod can run on the control plane (default "node-role.kubernetes.io/master")
  -use-dynamic-storage
    	Create a PVC for dynamic storage
  -use-nfs
    	Denotes whether the PVC uses NFS or not
  -use-pvc
    	Does the backup pod use a PVC? If not, dump it backup to local directory (default true)
```

### Eamples:

**NOTE:** In order to run as a normal linux cronjob you may want to use the `-oc-binary-path` option when calling this program

Create a backup with an NFS PVC:

```
./etcdBackup -kube-config=/home/stratus/temp/kubeconfig -use-nfs=true -debug=true -etcd-backup-project=backup-etcd -use-pvc=true -nfs-server=192.168.111.115 -nfs-path=/storage/etcd_backups -taint="node-role.kubernetes.io/master"
```

Create a backup with a dynamic PVC:

```
./etcdBackup -kube-config=/home/stratus/temp/kubeconfig -debug=true -etcd-backup-project=backup-etcd -use-pvc=true -use-dynamic-storage -taint="node-role.kubernetes.io/master"
```

Create a backup with both NFS and Dynamic PVC (backup file copied to both locations):

```
./etcdBackup -kube-config=/home/stratus/temp/kubeconfig -debug=true -etcd-backup-project=backup-etcd -use-pvc=true -nfs-server=192.168.111.115 -nfs-path=/storage/etcd_backups -taint="node-role.kubernetes.io/master" -use-dynamic-storage -use-nfs
```

Create a local backup:
```
./etcdBackup -kube-config=/home/stratus/temp/kubeconfig -debug=true -etcd-backup-project=backup-etcd -use-pvc=false -taint="node-role.kubernetes.io/master" -local-backup-dir=.
```


## Future Enhancements

In the future it may be possible to use a dynamically provisioned PV or have different storage backends
