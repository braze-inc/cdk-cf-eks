from typing import Dict, List

import aws_cdk.aws_eks as eks
import aws_cdk.aws_iam as iam
from aws_cdk import core as cdk
from aws_cdk.aws_s3 import Bucket

# Permission groups

s3_write_permissions = [
    "s3:GetObject",
    "s3:PutObject",
    "s3:DeleteObject",
    "s3:ListMultipartUploadParts",
    "s3:AbortMultipartUpload",
]

s3_read_permissions = [
    "s3:GetObject",
]

ecr_policies = {
    "ecr_read_write_policy": [
        "ecr:PutImageTagMutability",
        "ecr:StartImageScan",
        "ecr:ListTagsForResource",
        "ecr:UploadLayerPart",
        "ecr:BatchDeleteImage",
        "ecr:ListImages",
        "ecr:DeleteRepository",
        "ecr:CompleteLayerUpload",
        "ecr:TagResource",
        "ecr:DescribeRepositories",
        "ecr:DeleteRepositoryPolicy",
        "ecr:BatchCheckLayerAvailability",
        "ecr:ReplicateImage",
        "ecr:GetLifecyclePolicy",
        "ecr:PutLifecyclePolicy",
        "ecr:DescribeImageScanFindings",
        "ecr:GetLifecyclePolicyPreview",
        "ecr:CreateRepository",
        "ecr:PutImageScanningConfiguration",
        "ecr:GetDownloadUrlForLayer",
        "ecr:DeleteLifecyclePolicy",
        "ecr:PutImage",
        "ecr:UntagResource",
        "ecr:BatchGetImage",
        "ecr:DescribeImages",
        "ecr:StartLifecyclePolicyPreview",
        "ecr:InitiateLayerUpload",
        "ecr:GetRepositoryPolicy",
    ]
}

# The bucket policies are auto-generated from the bucket list with the names write-name, read-name. E.g. write_blobs

# Roles. The roles are the collection of the policies.
roles = {
    # E.g. nucleus needs this role
    "write_blobs_read_logs": [
        "write_blobs",
        "read_logs",
    ],
    # E.g. executor needs this role
    "write_blobs": [
        "write_blobs",
    ],
    # E.g. builder needs this role
    "write_images": [
        "ecr_read_write_policy",
    ],
}


class DominoEksK8sIamRolesProvisioner:
    def __init__(
        self,
        scope: cdk.Construct,
    ) -> None:
        self.scope = scope

    def provision(self, stack_name: str, cluster: eks.Cluster, buckets: Dict[str, Bucket]):
        # Create dummy service account just to make EKS to do heavy listing of creating OIDC
        # TODO: perform associate_iam_oidc_provider by lambda so we do  not create dummy stuff
        sa = eks.ServiceAccount(cluster, "dummy", cluster=cluster, name="dummy")
        # Then we copy policy doc
        statement_json = sa.role.assume_role_policy.to_json()['Statement'][0]
        del statement_json['Condition']['StringEquals']
        logical_id = self.scope.get_logical_id(
            # Warning! Magic! We go two levels deep because child OpenIdConnectProvider is type Construct but
            # logical_id belongs to type CfnElement, which is linked from below like this.
            cluster.node.find_child("OpenIdConnectProvider").node.default_child.node.default_child
        )
        fn = cdk.Fn.select(
            1,
            cdk.Fn.split(
                ":oidc-provider/",
                cdk.Fn.ref(logical_id),
            ),
        )
        statement_json['Condition']['StringLike'] = cdk.CfnJson(
            self.scope, "OidcJson", value={f"{fn}:aud": "sts.amazonaws.com", f"{fn}:sub": "system:serviceaccount:*"}
        )
        managed_policies = {}
        for name, cfg in ecr_policies.items():
            managed_policies[name] = self.create_ecr_policy(stack_name, name, cfg)

        managed_policies.update(self.create_s3_policies(stack_name, buckets))

        for name, policy_list in roles.items():
            iam_role = iam.Role(
                self.scope,
                f"{stack_name}-IAM-role-for-k8s-{name}",
                # Undesired side effect of this: additional statement is created to trust this principal.
                # Because Role constructor mandates principal and creates assume_role_policy
                # with this statement. And later we cannot neither replace assume_role_policy nor remove this statement.
                # Potentially we can avoid this by using CnfRole but no examples exist. A guesswork can take a week.
                assumed_by=iam.ServicePrincipal('eks.amazonaws.com'),
                role_name=f"{stack_name}-IAM-role-for-k8s-{name}",
            )
            iam_role.assume_role_policy.add_statements(iam.PolicyStatement.from_json(statement_json))
            for policy_name in policy_list:
                iam_role.add_managed_policy(managed_policies[policy_name])

    def create_ecr_policy(self, stack_name: str, policy_name: str, actions: List[str]):
        return iam.ManagedPolicy(
            self.scope,
            f"{stack_name}-{policy_name}-ECR",
            managed_policy_name=f"{stack_name}-{policy_name}-ECR",
            statements=[
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=actions,
                    resources=["*"],
                ),
                iam.PolicyStatement(
                    effect=iam.Effect.DENY,
                    actions=["ecr:*"],
                    conditions={"StringNotEqualsIfExists": {"ecr:ResourceTag/domino-deploy-id": stack_name}},
                    resources=[f"arn:aws:ecr:*:{self.scope.account}:*"],
                ),
            ],
        )

    def create_s3_policies(self, stack_name: str, buckets: Dict[str, Bucket]) -> Dict[str, iam.ManagedPolicy]:
        policies = {}
        for name, bucket in buckets.items():
            policies[f"read_{name}"] = iam.ManagedPolicy(
                self.scope,
                f"{stack_name}-read-{name}",
                managed_policy_name=f"{stack_name}-read-{name}",
                statements=[
                    iam.PolicyStatement(
                        actions=s3_read_permissions,
                        resources=[f"{bucket.bucket_arn}*"],
                    )
                ],
            )
            policies[f"write_{name}"] = iam.ManagedPolicy(
                self.scope,
                f"{stack_name}-write-{name}",
                managed_policy_name=f"{stack_name}-write-{name}",
                statements=[
                    iam.PolicyStatement(
                        actions=s3_write_permissions,
                        resources=[f"{bucket.bucket_arn}*"],
                    )
                ],
            )
        return policies
