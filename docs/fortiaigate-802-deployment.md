# FortiAIGate 8.0.2 AWS Development Deployment

The 8.0.2 deployment path is under live validation. Use only on an isolated
single-node lab with trusted ingress sources. The chart's L4 profile is marked
development-only; it is not a production hardware recommendation. The existing
`ingress-nginx` controller is retired upstream and must be replaced before
production exposure.

After the [AWS k3s foundation](aws-k3s-foundation.md) is ready and the 8.0.2
images are in ECR, run from the repository root:

```bash
ansible-playbook -i ansible/inventory/aws.generated.ini ansible/playbooks/deploy_fortiaigate.yml
```

Before Helm submission, the role pre-pulls the model, vLLM and Triton images
into the node cache with temporary pods and the namespace pull secret. Set
`fortiaigate_prefetch_images: false` to skip this stage. Image availability is
verified in k3s; an image lacking `/bin/true` can report a pod execution error
after its successful pull. The pod is cleaned up after verification. Cache hits and cold pre-pulls of all three large ECR images were verified on
a fresh AWS host.

This initial path supports the EC2 instance-role ECR token source. It refreshes
the namespace image-pull secret at startup and every six hours through a
root-owned systemd timer. AWS registry tokens expire, so check the timer and
service if subsequent image pulls fail:

```bash
sudo systemctl status fortiaigate-ecr-refresh.timer
sudo systemctl status fortiaigate-ecr-refresh.service
kubectl -n fortiaigate get pods,pvc,ingress
```

GPU profile and attachment are configured by `fortiaigate_gpu_profile` and
`fortiaigate_vllm_gpu_attach`; the tracked defaults are `l4` and `shared` for
the first L4 lab. Set an appropriate profile in ignored `user.yml` when using a
different GPU. Dedicated attachment needs additional allocatable GPUs and
licensing. The local-path storage post-render patch uses ReadWriteOnce for the
vendor's shared PVC; all consuming pods must stay on the same node. Multi-node
installations require a properly configured shared storage class.

For a CPU-only experiment, set `fortiaigate_gpu_enabled: false` in ignored
user vars and redeploy. The chart does not run vLLM in this mode; Fortinet's
guide says DLP and Natural Language detectors are unavailable. Policies using
Natural Language detectors can fail closed, so use a suitable test policy.
CPU-only licensing and functional behavior still require validation.

The chart creates a master-key Secret and uses a Kubernetes lookup to retain it
across Helm upgrades. The Secret is marked to survive Helm uninstall, but not
namespace deletion, cluster loss or a rebuild. Back it up securely with the
associated application database before changing or destroying the cluster.
Never commit its contents. Restore the same key with its database or stored
credentials cannot be decrypted.

The 8.0.2 license is uploaded after install through the administrator GUI or
supported API, rather than being staged into the Helm chart. A successful Helm
submission does not mean the application, GPU model, license or scanning is
ready. Check pod and application health and validate a licensed request before
using the deployment.
