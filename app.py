import aws_cdk as cdk

from aws_check.aws_check_stack import AwsCheckStack


app = cdk.App()
AwsCheckStack(app, "AwsCheckStack")

app.synth()
