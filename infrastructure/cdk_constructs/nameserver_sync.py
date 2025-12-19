"""Custom Resource to sync Route 53 hosted zone nameservers to domain registration."""

from aws_cdk import CustomResource, Duration
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_route53 as route53
from aws_cdk import custom_resources as cr
from constructs import Construct


class NameserverSync(Construct):
  """Auto-sync hosted zone nameservers to Route 53 domain registration.

  This Custom Resource calls the UpdateDomainNameservers API to automatically
  update the domain's nameservers to match the hosted zone. Only works for
  domains registered in Route 53.
  """

  def __init__(
    self,
    scope: Construct,
    id: str,
    *,
    domain_name: str,
    hosted_zone: route53.IHostedZone,
    resource_prefix: str = "",
  ) -> None:
    super().__init__(scope, id)

    # Lambda function to update nameservers
    handler = lambda_.Function(
      self,
      f"{resource_prefix}-ns-sync-lambda" if resource_prefix else "Handler",
      function_name=f"{resource_prefix}-ns-sync" if resource_prefix else None,
      runtime=lambda_.Runtime.PYTHON_3_12,
      handler="index.handler",
      code=lambda_.Code.from_inline(self._get_handler_code()),
      timeout=Duration.seconds(120),
    )

    # Grant permissions to update domain nameservers
    handler.add_to_role_policy(
      iam.PolicyStatement(
        actions=[
          "route53domains:UpdateDomainNameservers",
          "route53domains:GetDomainDetail",
        ],
        resources=["*"],  # Route53 Domains API doesn't support resource-level perms
      )
    )

    # Grant permissions to get hosted zone info
    handler.add_to_role_policy(
      iam.PolicyStatement(
        actions=["route53:GetHostedZone"],
        resources=[hosted_zone.hosted_zone_arn],
      )
    )

    # Create the Custom Resource provider
    provider = cr.Provider(
      self,
      f"{resource_prefix}-ns-sync-provider" if resource_prefix else "Provider",
      on_event_handler=handler,
    )

    # Create the Custom Resource
    self.custom_resource = CustomResource(
      self,
      f"{resource_prefix}-ns-sync-resource" if resource_prefix else "Resource",
      service_token=provider.service_token,
      properties={
        "DomainName": domain_name,
        "HostedZoneId": hosted_zone.hosted_zone_id,
      },
    )

  def _get_handler_code(self) -> str:
    return """
import boto3
import cfnresponse

def handler(event, context):
    try:
        request_type = event["RequestType"]
        props = event["ResourceProperties"]
        domain_name = props["DomainName"]
        hosted_zone_id = props["HostedZoneId"]

        if request_type == "Delete":
            # On delete, we don't revert nameservers - just succeed
            cfnresponse.send(event, context, cfnresponse.SUCCESS, {})
            return

        # Get hosted zone nameservers
        route53 = boto3.client("route53")
        hz_response = route53.get_hosted_zone(Id=hosted_zone_id)
        nameservers = hz_response["DelegationSet"]["NameServers"]

        print(f"Hosted zone nameservers: {nameservers}")

        # Update domain registration nameservers
        route53domains = boto3.client("route53domains", region_name="us-east-1")

        # Check if domain is registered in Route 53
        try:
            domain_detail = route53domains.get_domain_detail(DomainName=domain_name)
            current_ns = [ns["Name"] for ns in domain_detail.get("Nameservers", [])]
            print(f"Current domain nameservers: {current_ns}")
        except route53domains.exceptions.InvalidInput:
            print(f"Domain {domain_name} not registered in Route 53")
            cfnresponse.send(event, context, cfnresponse.SUCCESS, {
                "Message": f"Domain {domain_name} not registered in Route 53, skipping"
            })
            return
        except Exception as e:
            print(f"Could not get domain detail: {e}")
            cfnresponse.send(event, context, cfnresponse.SUCCESS, {
                "Message": f"Could not access domain {domain_name}: {str(e)}"
            })
            return

        # Check if nameservers already match
        if set(nameservers) == set(current_ns):
            print("Nameservers already match, no update needed")
            cfnresponse.send(event, context, cfnresponse.SUCCESS, {
                "Message": "Nameservers already in sync"
            })
            return

        # Update nameservers
        response = route53domains.update_domain_nameservers(
            DomainName=domain_name,
            Nameservers=[{"Name": ns} for ns in nameservers]
        )

        operation_id = response.get("OperationId")
        print(f"Updated nameservers, operation ID: {operation_id}")

        cfnresponse.send(event, context, cfnresponse.SUCCESS, {
            "OperationId": operation_id,
            "Nameservers": ",".join(nameservers)
        })

    except Exception as e:
        print(f"Error: {e}")
        cfnresponse.send(event, context, cfnresponse.FAILED, {"Error": str(e)})
"""
