from aws_cdk.region_info import Fact, FactName


# Future TODO item: Incorporate IAM reqs into the provisioning
# classes so we can generate exact perms for a given deployment
def generate_iam(stack_name: str, aws_account_id: str, region: str, manual: bool = False, use_bastion: bool = False):
    partition = Fact.require_fact(region, FactName.PARTITION)

    if manual:
        asset_bucket = "*"
    else:
        asset_bucket = "cdktoolkit-stagingbucket-*"

    from_cf_condition = {
        "Condition": {"ForAnyValue:StringEquals": {"aws:CalledVia": ["cloudformation.amazonaws.com"]}},
    }

    # temp function to preserve ordering while testing/comparing
    def do_cf():
        if manual:
            return {}
        else:
            return from_cf_condition

    cloudformation = {
        "Effect": "Allow",
        "Action": [
            "cloudformation:CreateChangeSet",
            "cloudformation:DeleteChangeSet",
            "cloudformation:DeleteStack",
            "cloudformation:DescribeChangeSet",
            "cloudformation:DescribeStackEvents",
            "cloudformation:DescribeStacks",
            "cloudformation:ExecuteChangeSet",
            "cloudformation:GetTemplate",
        ],
        "Resource": [
            # f"arn:aws:cloudformation:*:{aws_account_id}:stack/{stack_name}-eks-stack/*",
            f"arn:{partition}:cloudformation:*:{aws_account_id}:stack/{stack_name}*",
        ],
    }

    if not manual:
        cloudformation["Resource"].append(f"arn:{partition}:cloudformation:*:{aws_account_id}:stack/CDKToolkit/*")

    asset_bucket = {
        "Effect": "Allow",
        "Action": ["s3:*Object", "s3:GetBucketLocation", "s3:ListBucket"],
        "Resource": [f"arn:{partition}:s3:::{asset_bucket}"],
    }

    s3 = {
        "Effect": "Allow",
        "Action": [
            "s3:CreateBucket",
            "s3:DeleteBucket",
            "s3:DeleteBucketPolicy",
            "s3:GetBucketLocation",
            "s3:GetBucketPolicy",
            "s3:ListBucket",
            "s3:PutAccountPublicAccessBlock",
            "s3:PutBucketAcl",
            "s3:PutBucketLogging",
            "s3:PutBucketPolicy",
            "s3:PutBucketTagging",
            "s3:PutBucketVersioning",
            "s3:PutBucketPublicAccessBlock",
            "s3:PutEncryptionConfiguration",
        ],
        **do_cf(),
        "Resource": [f"arn:{partition}:s3:::{stack_name}-*"],
    }

    iam = {
        "Effect": "Allow",
        "Action": [
            "iam:AddRoleToInstanceProfile",
            "iam:AttachRolePolicy",
            "iam:CreateInstanceProfile",
            "iam:CreatePolicy",
            "iam:CreatePolicyVersion",
            "iam:CreateRole",
            "iam:CreateServiceLinkedRole",
            "iam:DeleteInstanceProfile",
            "iam:DeletePolicy",
            "iam:DeletePolicyVersion",
            "iam:DeleteRole",
            "iam:DeleteRolePolicy",
            "iam:DetachRolePolicy",
            "iam:GetInstanceProfile",
            "iam:GetPolicy",
            "iam:GetRole",
            "iam:ListAttachedRolePolicies",
            "iam:ListPolicyVersions",
            "iam:PassRole",
            "iam:PutRolePolicy",
            "iam:RemoveRoleFromInstanceProfile",
        ],
        **do_cf(),
        "Resource": [
            f"arn:{partition}:iam::{aws_account_id}:policy/{stack_name}-*",
            f"arn:{partition}:iam::{aws_account_id}:role/{stack_name}-*",
            f"arn:{partition}:iam::{aws_account_id}:instance-profile/{stack_name}-*",
            f"arn:{partition}:iam::{aws_account_id}:role/aws-service-role/autoscaling.amazonaws.com/AWSServiceRoleForAutoScaling",
        ],
    }

    if manual:
        iam["Action"].remove("iam:GetRole")
        iam["Action"].extend(["iam:Tag*", "iam:Untag*"])

    # TODO TF: lambda invoke block un-hack
    lambda_invoke = [
        {
            "Effect": "Allow",
            "Action": ["lambda:InvokeFunction"],
            "Resource": [f"arn:{partition}:lambda:*:{aws_account_id}:function:{stack_name}-*"],
        }
    ]

    if not manual:
        lambda_invoke = []

    _lambda = {
        "Effect": "Allow",
        "Action": [
            "lambda:CreateFunction",
            "lambda:UpdateFunctionCode",
            "lambda:DeleteFunction",
            "lambda:DeleteLayerVersion",
            "lambda:GetFunction",
            "lambda:GetLayerVersion",
            "lambda:GetLayerVersionPolicy",
            "lambda:InvokeFunction",
            "lambda:PublishLayerVersion",
            "lambda:UpdateFunctionConfiguration",
            "lambda:ListTags",
            "lambda:TagResource",
            "lambda:UntagResource",
        ],
        **from_cf_condition,
        "Resource": [
            f"arn:{partition}:lambda:*:{aws_account_id}:function:{stack_name}-*",
            f"arn:{partition}:lambda:*:{aws_account_id}:layer:*",
        ],
    }

    states = {
        "Effect": "Allow",
        "Action": [
            "states:CreateStateMachine",
            "states:DeleteStateMachine",
            "states:DescribeStateMachine",
            "states:TagResource",
            "states:UntagResource",
            "states:UpdateStateMachine",
        ],
        **from_cf_condition,
        "Resource": [f"arn:{partition}:states:*:{aws_account_id}:stateMachine:Provider*"],
    }

    # TODO: Below CF only
    eks_nodegroups = [
        {
            "Effect": "Allow",
            "Action": [
                "eks:CreateNodegroup",
                "eks:DeleteNodegroup",
                "eks:DescribeNodegroup",
                "eks:TagResource",
                "eks:UntagResource",
            ],
            "Resource": [f"arn:{partition}:eks:*:{aws_account_id}:cluster/*"],
        }
    ]

    if manual:
        eks_nodegroups = []

    cfn_tagging = {
        "Effect": "Allow",
        "Action": [
            "ssm:AddTagsToResource",
            "ssm:DeleteParameter",
            "ssm:PutParameter",
            "ssm:RemoveTagsFromResource",
        ],
        **from_cf_condition,
        "Resource": [f"arn:{partition}:ssm:*:{aws_account_id}:parameter/CFN*"],
    }

    ssm = {
        "Effect": "Allow",
        "Action": ["ssm:GetParameters"],
        "Resource": [
            f"arn:{partition}:ssm:*::parameter/aws/service/eks/*",
            f"arn:{partition}:ssm:*::parameter/aws/service/ami-amazon-linux-latest/*",
        ],
    }

    # TODO: TF-only version of this list
    backup_plan = f"{stack_name}-efs"
    if manual:
        backup_plan = "*"

    backup = {
        "Effect": "Allow",
        "Action": [
            "backup:*BackupVault*",
            "backup:CreateBackupPlan",
            "backup:CreateBackupSelection",
            "backup:DeleteBackupPlan",
            "backup:DeleteBackupSelection",
            "backup:GetBackupPlan",
            "backup:GetBackupSelection",
            "backup:ListTags",
            "backup:TagResource",
            "backup:UntagResource",
        ],
        **from_cf_condition,
        "Resource": [
            f"arn:{partition}:backup:*:{aws_account_id}:backup-vault:{stack_name}-efs",
            f"arn:{partition}:backup:*:{aws_account_id}:backup-plan:{backup_plan}",
        ],
    }

    if manual:
        backup["Action"].remove("backup:CreateBackupPlan")
        backup["Action"].remove("backup:DeleteBackupPlan")
        backup["Action"].remove("backup:GetBackupPlan")
        backup["Action"].insert(0, "backup:*BackupPlan")

    backup_efs = [
        {
            "Effect": "Allow",
            "Action": [
                "backup-storage:MountCapsule",
                "elasticfilesystem:CreateAccessPoint",
                "elasticfilesystem:CreateFileSystem",
                "elasticfilesystem:DeleteAccessPoint",
                "elasticfilesystem:DeleteFileSystem",
                "elasticfilesystem:DescribeAccessPoints",
                "elasticfilesystem:DescribeFileSystems",
                "elasticfilesystem:ModifyMountTargetSecurityGroups",
            ],
            **from_cf_condition,
            "Resource": "*",
        }
    ]

    if not manual:
        backup_efs = []

    kms = {
        "Effect": "Allow",
        "Action": [
            "kms:CreateGrant",
            "kms:CreateAlias",
            "kms:CreateKey",
            "kms:DeleteAlias",
            "kms:DescribeKey",
            "kms:EnableKeyRotation",
            "kms:GenerateDataKey",
            "kms:PutKeyPolicy",
            "kms:RetireGrant",
            "kms:ScheduleKeyDeletion",
            "kms:TagResource",
            "kms:UpdateAlias",
        ],
        **from_cf_condition,
        "Resource": "*",
    }

    ecr = [
        {
            "Effect": "Allow",
            "Action": ["ecr:CreateRepository", "ecr:DeleteRepository"],
            "Condition": {"ForAnyValue:StringEquals": {"aws:CalledVia": ["cloudformation.amazonaws.com"]}},
            "Resource": [f"arn:{partition}:ecr:*:{aws_account_id}:repository/{stack_name}*"],
        }
    ]

    if not manual:
        ecr = []

    bastion = []

    if use_bastion:
        bastion = [
            {
                "Effect": "Allow",
                "Action": [
                    "ec2:TerminateInstances",
                ],
                "Resource": "*",
                "Condition": {
                    "StringEquals": {
                        "ec2:ResourceTag/domino-deploy-id": stack_name,
                    }
                },
            },
        ]

    flow_logs = {
        "Effect": "Allow",
        "Action": [
            "ec2:CreateFlowLogs",
            "ec2:DescribeFlowLogs",
            "ec2:DeleteFlowLogs",
            "logs:CreateLogDelivery",
            "logs:DeleteLogDelivery",
        ],
        **from_cf_condition,
        "Resource": "*",
    }

    acm = {
        "Effect": "Allow",
        "Action": [
            "acm:AddTagsToCertificate",
            "acm:DeleteCertificate",
            "acm:DescribeCertificate",
            "acm:GetCertificate",
            "acm:ListTagsForCertificate",
            "acm:RemoveTagsFromCertificate",
            "acm:RequestCertificate",
        ],
        **from_cf_condition,
        "Resource": f"arn:{partition}:acm:*:{aws_account_id}:certificate/*",
    }

    general = {
        "Effect": "Allow",
        "Action": [
            "acm:AddTagsToCertificate",
            "acm:DeleteCertificate",
            "acm:DescribeCertificate",
            "acm:GetCertificate",
            "acm:ListTagsForCertificate",
            "acm:RemoveTagsFromCertificate",
            "acm:RequestCertificate",
            "autoscaling:CreateAutoScalingGroup",
            "autoscaling:CreateOrUpdateTags",
            "autoscaling:DeleteAutoScalingGroup",
            "autoscaling:DeleteTags",
            "autoscaling:DescribeAutoScalingGroups",
            "autoscaling:DescribeScalingActivities",
            "autoscaling:DescribeScheduledActions",
            "autoscaling:UpdateAutoScalingGroup",
            "ec2:*NetworkInterface*",
            "ec2:*Subnet*",
            "ec2:AllocateAddress",
            "ec2:AssociateAddress",
            "ec2:AuthorizeSecurityGroupEgress",
            "ec2:AuthorizeSecurityGroupIngress",
            "ec2:CreateLaunchTemplate",
            "ec2:CreateLaunchTemplateVersion",
            "ec2:CreateSecurityGroup",
            "ec2:CreateTags",
            "ec2:DeleteLaunchTemplate",
            "ec2:DeleteSecurityGroup",
            "ec2:DeleteTags",
            "ec2:DescribeAccountAttributes",
            "ec2:DescribeAddresses",
            "ec2:DescribeAvailabilityZones",
            "ec2:DescribeImages",
            "ec2:DescribeInstances",
            "ec2:DescribeLaunchTemplates",
            "ec2:DescribeSecurityGroups",
            "ec2:DisassociateAddress",
            "ec2:GetLaunchTemplateData",
            "ec2:ModifyInstanceMetadataOptions",
            "ec2:ReleaseAddress",
            "ec2:RevokeSecurityGroupEgress",
            "ec2:RevokeSecurityGroupIngress",
            "ec2:RunInstances",
            "eks:*Addon*",
            "eks:CreateNodegroup",
            "eks:DeleteNodegroup",
            "eks:DescribeNodegroup",
            "eks:DescribeUpdate",
            "eks:ListTagsForResource",
            "eks:TagResource",
            "eks:UntagResource",
            "elasticfilesystem:Backup",
            "elasticfilesystem:CreateMountTarget",
            "elasticfilesystem:DeleteMountTarget",
            "elasticfilesystem:DescribeFileSystemPolicy",
            "elasticfilesystem:DescribeMountTargets",
            "elasticfilesystem:ListTagsForResource",
            "elasticfilesystem:TagResource",
            "elasticfilesystem:UntagResource",
            "iam:GetRole",
            "iam:GetRolePolicy",
            "route53:ChangeResourceRecordSets",
        ],
        **do_cf(),
        "Resource": "*",
    }
    if not manual:
        general["Action"].extend(
            [
                "backup-storage:MountCapsule",
                "backup:*BackupPlan",
                "backup:*BackupSelection",
                "ec2:AssociateRouteTable",
                "ec2:AssociateVpcCidrBlock",
                "ec2:AttachInternetGateway",
                "ec2:CreateInternetGateway",
                "ec2:CreateNatGateway",
                "ec2:CreateRoute",
                "ec2:CreateRouteTable",
                "ec2:CreateVpc",
                "ec2:CreateVpcEndpoint",
                "ec2:DeleteInternetGateway",
                "ec2:DeleteNatGateway",
                "ec2:DeleteRoute",
                "ec2:DeleteRouteTable",
                "ec2:DeleteVpc",
                "ec2:DeleteVpcEndpoints",
                "ec2:Describe*",
                "ec2:DetachInternetGateway",
                "ec2:DisAssociateRouteTable",
                "ec2:DisassociateVpcCidrBlock",
                "ec2:ModifyVpcAttribute",
                "elasticfilesystem:CreateAccessPoint",
                "elasticfilesystem:CreateFileSystem",
                "elasticfilesystem:DeleteAccessPoint",
                "elasticfilesystem:DeleteFileSystem",
                "elasticfilesystem:DescribeAccessPoints",
                "elasticfilesystem:DescribeFileSystems",
                "iam:ListAttachedRolePolicies",
            ]
        )
    else:
        general["Action"].extend(
            [
                "ec2:Describe*",
                "ec2:*InternetGateway*",
                "ec2:*NatGateway*",
                "ec2:*Route*",
                "ec2:*Vpc*",
                "s3:GetBucketLocation",
                "s3:GetObject",
                "s3:ListBucket",
            ]
        )
        general["Resource"] = ["*"]
    general["Action"] = sorted(general["Action"])

    policies = [
        {
            "Version": "2012-10-17",
            "Statement": [
                cloudformation,
                asset_bucket,
                s3,
                iam,
                *lambda_invoke,
                _lambda,
                states,
                *eks_nodegroups,
                cfn_tagging,
                ssm,
                flow_logs,
            ],
        },
        {
            "Version": "2012-10-17",
            "Statement": [
                backup,
                *backup_efs,
                *ecr,
                *bastion,
                general,
                kms,
                acm,
            ],
        },
    ]

    return policies
