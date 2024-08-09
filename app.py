import aws_cdk as cdk

from aws_check.aws_check_stack import AwsCheckStack

app = cdk.App()

user_name = app.node.get_context("user_name")

AwsCheckStack(app, "AwsCheckStack", user_name=user_name)


app.synth()
