import cdk_eks_karpenter as eks_karpenter
from aws_cdk import CfnOutput, RemovalPolicy, Stack
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_eks as eks
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from aws_cdk.lambda_layer_kubectl_v30 import KubectlV30Layer
from constructs import Construct


class AwsCheckStack(Stack):
    def __init__(
        self, scope: Construct, construct_id: str, user_name: str, **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # # VPC
        # vpc = ec2.Vpc(self, "Vpc")

        # IAM
        user = iam.User.from_user_name(self, "User", user_name)

        # S3
        bucket = s3.Bucket(
            self,
            "Bucket",
            auto_delete_objects=True,  # TODO: 本番環境ではFalseにする
            removal_policy=RemovalPolicy.DESTROY,  # TODO: 本番環境で変えるか考える
        )
        CfnOutput(self, "BucketName", key="Bucket", value=bucket.bucket_name)

        # EKS
        cluster = eks.Cluster(
            self,
            "Cluster",
            version=eks.KubernetesVersion.V1_30,
            kubectl_layer=KubectlV30Layer(self, "KubectlLayer"),
            default_capacity=0,
            core_dns_compute_type=eks.CoreDnsComputeType.FARGATE,
        )
        cluster.aws_auth.add_user_mapping(user, groups=["system:masters"])
        CfnOutput(self, "ClusterName", key="Cluster", value=cluster.cluster_name)

        # Karpenter
        cluster.add_fargate_profile(
            "karpenter",
            selectors=[
                {"namespace": "karpenter"},
                {
                    "namespace": "kube-system",
                    "labels": {"k8s-app": "kube-dns"},
                },
            ],
        )

        karpenter = eks_karpenter.Karpenter(
            self,
            "Karpenter",
            cluster=cluster,
            version="0.37.0",
        )

        node_class = karpenter.add_ec2_node_class(
            "node-class",
            {
                "amiFamily": "AL2",
                "subnetSelectorTerms": [  # NOTE: よくわかってないけどとりあえずプライベートsubnetを指定
                    {"id": subnet.subnet_id}
                    for subnet in cluster.vpc.select_subnets(
                        subnet_type=ec2.SubnetType.PRIVATE_WITH_NAT
                    ).subnets
                ],
                "securityGroupSelectorTerms": [
                    {"tags": {"aws:eks:cluster-name": cluster.cluster_name}}
                ],
                "role": karpenter.node_role.role_name,
            },
        )

        karpenter.add_node_pool(
            "node-pool",
            {
                "template": {
                    "spec": {
                        "nodeClassRef": {
                            "apiVersion": "karpenter.k8s.aws/v1beta1",
                            "kind": "EC2NodeClass",
                            "name": node_class["name"],
                        },
                        "requirements": [
                            {
                                "key": "kubernetes.io/arch",
                                "operator": "In",
                                "values": ["amd64"],
                            },
                            {
                                "key": "kubernetes.io/os",
                                "operator": "In",
                                "values": ["linux"],
                            },
                            {
                                "key": "karpenter.sh/capacity-type",
                                "operator": "In",
                                "values": ["spot"],
                            },
                            {
                                "key": "karpenter.k8s.aws/instance-category",
                                "operator": "In",
                                "values": ["c", "m", "r"],
                            },
                            {
                                "key": "karpenter.k8s.aws/instance-generation",
                                "operator": "Gt",
                                "values": ["2"],
                            },
                        ],
                    }
                }
            },
        )

        karpenter.add_managed_policy_to_karpenter_role(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                "AmazonSSMManagedInstanceCore"
            )
        )
