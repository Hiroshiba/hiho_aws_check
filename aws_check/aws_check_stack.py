from aws_cdk import CfnOutput, Duration, RemovalPolicy, Size, Stack
from aws_cdk import aws_batch as batch
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_s3 as s3
from constructs import Construct


class AwsCheckStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # NAT インスタンス
        # TODO: 自動アップデートを実装すべき
        nat_instance = ec2.NatProvider.instance_v2(
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.T4G, ec2.InstanceSize.NANO
            ),
            machine_image=ec2.MachineImage.latest_amazon_linux2023(
                cpu_type=ec2.AmazonLinuxCpuType.ARM_64
            ),
            default_allowed_traffic=ec2.NatTrafficDirection.OUTBOUND_ONLY,
        )

        # VPC
        vpc = ec2.Vpc(
            self,
            "Vpc",
            max_azs=1,
            nat_gateways=1,
            nat_gateway_provider=nat_instance,
            ip_protocol=ec2.IpProtocol.DUAL_STACK,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    cidr_mask=24,
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    map_public_ip_on_launch=True,
                ),
                ec2.SubnetConfiguration(
                    cidr_mask=24,
                    name="Private",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                ),
            ],
        )
        nat_instance.security_group.add_ingress_rule(
            peer=ec2.Peer.ipv4(vpc.vpc_cidr_block), connection=ec2.Port.all_traffic()
        )

        # Security Group
        security_group = ec2.SecurityGroup(
            self, "SecurityGroup", vpc=vpc, allow_all_ipv6_outbound=True
        )

        # S3
        bucket = s3.Bucket(
            self,
            "Bucket",
            auto_delete_objects=True,  # TODO: 本番環境ではFalseにする
            removal_policy=RemovalPolicy.DESTROY,  # TODO: 本番環境で変えるか考える
        )
        CfnOutput(self, "BucketName", key="Bucket", value=bucket.bucket_name)

        # Batch
        compute_environment = batch.ManagedEc2EcsComputeEnvironment(
            self,
            "ComputeEnvironment",
            vpc=vpc,
            security_groups=[security_group],
            spot=True,
            spot_bid_percentage=100,
            # instance_types=[],
            use_optimal_instance_classes=True,  # TODO: 念の為これFalseにしてinstance_types指定したほうが良いかも
            allocation_strategy=batch.AllocationStrategy.SPOT_PRICE_CAPACITY_OPTIMIZED,
            minv_cpus=0,
            maxv_cpus=256,
        )
        bucket.grant_read_write(compute_environment.instance_role)

        job_queue = batch.JobQueue(
            self,
            "JobQueue",
            job_queue_name="check-job-queue",
            compute_environments=[
                batch.OrderedComputeEnvironment(
                    compute_environment=compute_environment, order=1
                )
            ],
            job_state_time_limit_actions=[
                batch.JobStateTimeLimitAction(
                    max_time=Duration.minutes(10),
                    reason=batch.JobStateTimeLimitActionsReason.COMPUTE_ENVIRONMENT_MAX_RESOURCE,
                ),
                batch.JobStateTimeLimitAction(
                    max_time=Duration.minutes(10),
                    reason=batch.JobStateTimeLimitActionsReason.INSUFFICIENT_INSTANCE_CAPACITY,
                ),
                batch.JobStateTimeLimitAction(
                    max_time=Duration.minutes(10),
                    reason=batch.JobStateTimeLimitActionsReason.JOB_RESOURCE_REQUIREMENT,
                ),
            ],
        )

        container_definition = batch.EcsEc2ContainerDefinition(
            self,
            "ContainerDefinition",
            image=ecs.ContainerImage.from_registry(
                "public.ecr.aws/amazonlinux/amazonlinux:latest"
            ),
            cpu=1,
            memory=Size.mebibytes(1024),
            command=["echo", "Hello, World!"],  # TODO: 置き換え
            privileged=True,  # TODO: fuseを利用可能にするため。本当は避けた方が良い。
        )

        job_definition = batch.EcsJobDefinition(
            self,
            "JobDefinition",
            job_definition_name="check-job-definition",
            container=container_definition,
            retry_attempts=1,
            retry_strategies=[
                batch.RetryStrategy.of(
                    batch.Action.RETRY, batch.Reason.SPOT_INSTANCE_RECLAIMED
                )
            ],
        )
