# VPC Layout

This diagram shows the AWS network layout created by `terraform/aws-ec2-k3s`
and the supporting AWS resources prepared by `terraform/aws-prep`.

The default deployment mode is `k3s_subnet_mode = "public"`:

- the k3s EC2 host is placed in the k3s public subnet
- the host receives the prep-owned k3s Elastic IP
- SSH, HTTP, HTTPS, and demo NodePorts are allowed only from
  `allowed_ingress_cidr`
- the instance does not request an auto-assigned ephemeral public IP

Private k3s mode and FortiGate/FortiWeb appliance-fronted routing are planned
expansion paths. The appliance public and internal subnets exist now so the VPC
layout does not need to be redesigned later.

```mermaid
flowchart TB
    Operator["Operator workstation<br/>allowed_ingress_cidr"]
    Internet["Internet"]
    AWSAPI["AWS public APIs<br/>ECR, Bedrock, SSM, GitHub as needed"]

    subgraph Prep["terraform/aws-prep"]
        K3SEIP["k3s Elastic IP<br/>allocated before EC2"]
        FGEIP["FortiGate Elastic IP<br/>optional / future"]
        FWEIP["FortiWeb Elastic IP<br/>optional / future"]
        IAM["EC2 IAM role + instance profile<br/>ECR pull + optional Bedrock invoke"]
    end

    subgraph VPC["VPC 10.20.0.0/16"]
        IGW["Internet Gateway"]
        PublicRT["Public route table<br/>0.0.0.0/0 -> IGW"]

        subgraph K3SPublic["k3s public subnet<br/>10.20.1.0/24"]
            K3SPubENI["k3s EC2 ENI<br/>public mode"]
        end

        subgraph K3SPrivate["k3s private subnet<br/>10.20.2.0/24"]
            K3SPrivENI["k3s EC2 ENI<br/>private mode / future"]
        end

        subgraph FortiGatePublicSubnet["FortiGate public subnet<br/>10.20.10.0/24"]
            FortiGatePub["FortiGate port1 / management<br/>future"]
        end

        subgraph FortiGateInternalSubnet["FortiGate internal subnet<br/>10.20.20.0/24"]
            FortiGateInt["FortiGate port2 / internal<br/>future"]
        end

        subgraph FortiWebPublicSubnet["FortiWeb public subnet<br/>10.20.11.0/24"]
            FortiWebPub["FortiWeb public / management<br/>future"]
        end

        subgraph FortiWebInternalSubnet["FortiWeb internal subnet<br/>10.20.21.0/24"]
            FortiWebInt["FortiWeb internal<br/>future"]
        end

        SG["k3s security group<br/>trusted CIDRs only<br/>SSH, HTTP, HTTPS, demo ports"]

        subgraph K3S["Single-node k3s"]
            NodePorts["NodePort demo services<br/>30080-30084 HTTP<br/>30443-30447 optional HTTPS"]
            Ingress["ingress-nginx<br/>internal app routing"]
            Apps["FortiAIGate, LiteLLM,<br/>chatbot, MCP,<br/>optional Open WebUI"]
            Pods["Pod CIDR 10.60.0.0/16"]
            Services["Service CIDR 10.70.0.0/16<br/>DNS 10.70.0.10"]
        end
    end

    Operator -->|"SSH / HTTPS / NodePorts<br/>trusted CIDR only"| K3SEIP
    Internet --> IGW
    IGW --- PublicRT
    PublicRT --- K3SPublic
    PublicRT --- FortiGatePublicSubnet
    PublicRT --- FortiWebPublicSubnet

    K3SEIP --> K3SPubENI
    K3SPubENI --- SG
    SG --- NodePorts
    NodePorts --> Ingress
    Ingress --> Apps
    Apps --- Pods
    Apps --- Services

    IAM -.->|"attached to EC2 instance"| K3SPubENI
    K3SPubENI -->|"ECR pulls / Bedrock invoke"| AWSAPI

    FGEIP -.->|"future public entry"| FortiGatePub
    FWEIP -.->|"future public entry"| FortiWebPub
    FortiGatePub -.-> FortiGateInt
    FortiWebPub -.-> FortiWebInt
    FortiGateInt -.->|"future private ingress / NAT / inspection"| K3SPrivENI
    FortiWebInt -.->|"future HTTP/S publishing"| K3SPrivENI
    K3SPrivENI -.->|"private k3s mode"| SG

    classDef current fill:#e8f3ff,stroke:#2b6cb0,color:#111;
    classDef future fill:#fff7dc,stroke:#b7791f,color:#111,stroke-dasharray: 5 5;
    classDef external fill:#f4f4f5,stroke:#52525b,color:#111;

    class K3SEIP,IAM,K3SPubENI,SG,NodePorts,Ingress,Apps,Pods,Services current;
    class FortiGatePub,FortiGateInt,FortiWebPub,FortiWebInt,K3SPrivENI,FGEIP,FWEIP future;
    class Operator,Internet,AWSAPI external;
```

## Routing Notes

| Mode | k3s placement | Public access | Default route |
|---|---|---|---|
| `public` | k3s public subnet | k3s Elastic IP from AWS Prep | public route table to IGW |
| `private` | k3s private subnet | future FortiGate/FortiWeb path | future appliance/NAT path |

Current public mode is intentionally simple for repeatable demos. Private mode
should be used only after a management path and appliance-fronted ingress path
are in place.

## Related Values

| Value | Default |
|---|---|
| VPC CIDR | `10.20.0.0/16` |
| k3s public subnet | `10.20.1.0/24` |
| k3s private subnet | `10.20.2.0/24` |
| FortiGate public subnet | `10.20.10.0/24` |
| FortiWeb public subnet | `10.20.11.0/24` |
| FortiGate internal subnet | `10.20.20.0/24` |
| FortiWeb internal subnet | `10.20.21.0/24` |
| k3s pod CIDR | `10.60.0.0/16` |
| k3s service CIDR | `10.70.0.0/16` |
| k3s DNS | `10.70.0.10` |

Keep AWS VPC, k3s pod, and k3s service networks non-overlapping. Change these
values before cluster creation; changing k3s cluster networks after deployment
requires a rebuild.
