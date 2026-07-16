# VPC Layout

These diagrams separate the AWS network layout created by
`terraform/aws-ec2-k3s` from the supporting resources prepared by
`terraform/aws-prep`. Keeping prep resources out of the VPC drawing makes the
network diagram easier to read.

The default deployment mode is `k3s_subnet_mode = "public"`:

- the k3s EC2 host is placed in the k3s public subnet
- the host receives the prep-owned k3s Elastic IP
- SSH, HTTP, HTTPS, and demo NodePorts are allowed only from
  `allowed_ingress_cidr`
- the instance does not request an auto-assigned ephemeral public IP

FortiGate and FortiWeb are optional appliance deployments with public
management EIPs and internal ENIs. Private k3s mode and appliance-fronted
traffic paths remain planned expansion paths.

## VPC Network Topology

```mermaid
flowchart TB
    Operator["Operator workstation<br/>allowed_ingress_cidr"]
    Internet["Internet"]
    AWSAPI["AWS public APIs<br/>ECR, Bedrock, SSM, GitHub as needed"]
    K3SEIP["k3s EIP<br/>from aws-prep"]
    FGEIP["FortiGate EIP<br/>optional"]
    FWEIP["FortiWeb EIP<br/>optional"]

    subgraph VPC["VPC 10.20.0.0/16"]
        direction TB
        IGW["Internet Gateway"]
        PublicRT["Public route table<br/>0.0.0.0/0 -> IGW"]

        subgraph CurrentK3S["Current public k3s path"]
            direction TB
            K3SPubENI["k3s EC2 ENI<br/>public subnet 10.20.1.0/24"]
            SG["k3s security group<br/>trusted CIDRs only"]
            NodePorts["NodePort demo services<br/>30080-30084 HTTP<br/>30443-30447 optional HTTPS"]
            Ingress["ingress-nginx<br/>internal app routing"]
            Apps["FortiAIGate, LiteLLM,<br/>chatbot, MCP,<br/>optional Open WebUI"]
            Pods["Pod CIDR 10.60.0.0/16"]
            Services["Service CIDR 10.70.0.0/16<br/>DNS 10.70.0.10"]
        end

        subgraph OptionalAppliances["Optional appliance deployments"]
            direction TB
            subgraph FortiGate["FortiGate"]
                direction LR
                FortiGatePub["port1 management<br/>public subnet 10.20.10.0/24"]
                FortiGateInt["port2 internal<br/>internal subnet 10.20.20.0/24"]
            end
            subgraph FortiWeb["FortiWeb"]
                direction LR
                FortiWebPub["port1 management<br/>public subnet 10.20.11.0/24"]
                FortiWebInt["port2 internal<br/>internal subnet 10.20.21.0/24"]
            end
        end

        subgraph FuturePrivate["Future private k3s path"]
            K3SPrivENI["k3s EC2 ENI<br/>private subnet 10.20.2.0/24"]
        end
    end

    Operator -->|"SSH / HTTPS / NodePorts<br/>trusted CIDR only"| K3SEIP
    Internet --> IGW
    IGW --- PublicRT

    K3SEIP --> K3SPubENI
    PublicRT --- K3SPubENI
    K3SPubENI --- SG
    SG --- NodePorts
    NodePorts --> Ingress
    Ingress --> Apps
    Apps --- Pods
    Apps --- Services

    K3SPubENI -->|"ECR pulls / Bedrock invoke"| AWSAPI

    FGEIP -->|"management EIP"| FortiGatePub
    FWEIP -->|"management EIP"| FortiWebPub
    PublicRT --- FortiGatePub
    PublicRT --- FortiWebPub
    FortiGatePub --- FortiGateInt
    FortiWebPub --- FortiWebInt
    FortiGateInt -.->|"future private ingress / NAT / inspection"| K3SPrivENI
    FortiWebInt -.->|"future HTTP/S publishing"| K3SPrivENI
    K3SPrivENI -.->|"private k3s mode"| SG

    classDef current fill:#e8f3ff,stroke:#2b6cb0,color:#111;
    classDef appliance fill:#e8fff3,stroke:#2f855a,color:#111;
    classDef future fill:#fff7dc,stroke:#b7791f,color:#111,stroke-dasharray: 5 5;
    classDef external fill:#f4f4f5,stroke:#52525b,color:#111;

    class K3SEIP,K3SPubENI,SG,NodePorts,Ingress,Apps,Pods,Services current;
    class FGEIP,FWEIP,FortiGatePub,FortiGateInt,FortiWebPub,FortiWebInt appliance;
    class K3SPrivENI future;
    class Operator,Internet,AWSAPI external;
```

## Prep Resources And Module Dependencies

```mermaid
flowchart TB
    Common["terraform/user.tfvars<br/>profile, region, prefix, SSH key, CIDRs"]

    subgraph Prep["terraform/aws-prep"]
        K3SEIP["k3s Elastic IP"]
        FGEIP["FortiGate Elastic IP<br/>when enabled"]
        FWEIP["FortiWeb Elastic IP<br/>when enabled"]
        K3SIAM["k3s IAM role/profile<br/>ECR pull + optional Bedrock"]
        FWBIAM["FortiWeb IAM instance profile<br/>S3 cloud-init read"]
        FWBS3["FortiWeb S3 bucket<br/>config + license objects"]
    end

    subgraph Foundation["terraform/aws-ec2-k3s"]
        VPCModule["VPC, subnets, route tables"]
        K3SInstance["k3s EC2 instance"]
        GeneratedFiles["generated inventory<br/>generated port vars"]
    end

    subgraph Appliances["Optional Phase 4 appliances"]
        FGTModule["terraform/aws-fortigate<br/>two ENIs + EIP"]
        FWBModule["terraform/aws-fortiweb<br/>two ENIs + EIP + S3 user-data"]
    end

    Common --> Prep
    Common --> Foundation
    Common --> FGTModule
    Common --> FWBModule

    K3SEIP --> K3SInstance
    K3SIAM --> K3SInstance
    VPCModule --> FGTModule
    VPCModule --> FWBModule
    FGEIP --> FGTModule
    FWEIP --> FWBModule
    FWBIAM --> FWBModule
    FWBS3 --> FWBModule
    K3SInstance --> GeneratedFiles

    classDef prep fill:#f4f4f5,stroke:#52525b,color:#111;
    classDef current fill:#e8f3ff,stroke:#2b6cb0,color:#111;
    classDef appliance fill:#e8fff3,stroke:#2f855a,color:#111;

    class Common,K3SEIP,FGEIP,FWEIP,K3SIAM,FWBIAM,FWBS3 prep;
    class VPCModule,K3SInstance,GeneratedFiles current;
    class FGTModule,FWBModule appliance;
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
