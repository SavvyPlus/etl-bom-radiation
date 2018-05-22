# etl-bom-radiation

## Flow : 
From and upload file to special unzip we use the Unzip portal to move the data to input folder inside a bucket, and then we add partition yearl and mont to be query in athena. 

This is specifically for Radiation data and it loads ad-hoc when we get new Data 


#TO-DO

We need a description of this handlers, explaining the status of it and what needs to be done to get it into production together with a link to the asana task or tasks that have been involved, and hierarcchy of all the people involved in the project


## Wiki , after which we need to add a wiki page (inside github) to further expain the operation and function of this handler

# Intro
This project contains the lambda code and infrastructure to build a codepipeline for processing precis forecast files.

# Structure
```

```

The project contains a directory for the bom lambda `bom`.

Each directory contains the lambda python code and the corresponding requirements file.  The `buildspec.yaml` file is used by AWS CodeBuild to build the lambda with it's dependencies for deploying into the AWS Lambda infrastructure.

# Cloudformation
The main cloudformation file `bom.cfn.yaml` defines the BOM stack.  This file creates the
common AWS IAM permissions for the lambdas, defines general parameters, defines the build steps to build the lambdas and specifies an AWS CodePipeline with various stages.

## Sections
The `bom.cfn.yaml` file is split into sections; `Parameters`, `Metadata`, `Resources` and `Outputs`

### Parameters
These are used to configure the cloudformation stack and can be used to parameterise or override defaults in the cloudformation template that deploys the lambdas.

### Resources
These are the resources that cloudformation will create when executing this stack. In this stack, the resources include Roles with permissions, CodeBuild definitions for the lambdas, SNS topics for communication and the CodePipeline.

### CodeBuild Resource
```
CodeBuildBOMLambda:
  Type: AWS::CodeBuild::Project
  DependsOn: CloudFormationRole
  Properties:
    Artifacts:
      Type: CODEPIPELINE
    Environment:
      ComputeType: BUILD_GENERAL1_SMALL
      Image: aws/codebuild/python:3.5.2
      Type: LINUX_CONTAINER
    Name: 'CodeBuildTASHydroRateCardLambda'
    ServiceRole: !GetAtt CodeBuildRole.Arn
    Source:
      Type: CODEPIPELINE
      BuildSpec: 'tas-hydro-rate-card/buildspec.yaml'
    TimeoutInMinutes: 5 # must be between 5 minutes and 8 hours
    Cache:
      Location: 'foamdino-etl-build-cache'
      Type: S3
```
This is an example of one of the CodeBuild resources that is part of the stack.  In this we specify the version of the lambda container linux we want to use to build and we specify the `buildspec` file that should be executed to create the output.

### buildspec
```
version: 0.2

phases:
  install:
    commands:
      - pip install --upgrade pip
      - pip install -r tas-hydro-rate-card/requirements.txt -t tas-hydro-rate-card

artifacts:
  base-directory: tas-hydro-rate-card
  files:
    - '**/*'
  type: zip

cache:
  paths:
    - /root/.cache/pip
```
This is the corresponding `buildspec.yaml` for the CodeBuild step.  There can be many commands executed as part of various phases: https://docs.aws.amazon.com/codebuild/latest/userguide/build-spec-ref.html in this case though we just need to ensure that the dependencies are installed, so we use the `requirements.txt` file and `pip` to achieve this.

## CodePipeline
The core part of this cloudformation template is the `CodePipeline` definition.  This definition describes the CodePipeline and the stages that it is built from.

### Stage 1: GitHubSource
```
Name: GitHubSource
  Actions:
    - Name: TemplateSource
      ActionTypeId:
        Category: Source
        Owner: ThirdParty
        Version: 1
        Provider: GitHub
      Configuration:
        Owner: !Ref 'GitHubOwner'
        Repo: !Ref 'GitHubRepo'
        Branch: !Ref 'GitHubBranch'
        OAuthToken: !Ref 'GitHubToken'
      OutputArtifacts:
        - Name: SourceCode
      RunOrder: 1
```
This stage connects to the specified git repository and branch and downloads the source code.  The output of this stage is given the name `SourceCode` and this is then available to the following stages in the pipeline.

### Stage 2: BuildTASHydroLambdas
```
- Name: BuildTASHydroLambdas
  Actions:
    - Name: BuildTASHydroRateCardLambda
      ActionTypeId:
        Category: Build
        Owner: AWS
        Provider: CodeBuild
        Version: 1
      Configuration:
        ProjectName: !Ref CodeBuildTASHydroRateCardLambda
      InputArtifacts:
        - Name: SourceCode
      OutputArtifacts:
        - Name: BuildTASHydroRateCardLambdaOutput
```
This stage uses the output of the previous stage; `SourceCode` as the input for the task, which in this case is to run a `CodeBuild` task.  This task references the previously defined codebuild step and after execution the output of this is called `BuildTASHydroRateCardLambdaOutput`, which can be used in later stages of the pipeline.

### Stage 3: TestStage
This stage is broken into 3 pieces: `CreateLambdasAndDependencies`, `ApproveTestStack`, `DeleteTestStack`.
```
- Name: CreateLambdasAndDependencies
  ActionTypeId:
    Category: Deploy
    Owner: AWS
    Provider: CloudFormation
    Version: '1'
  InputArtifacts:
    - Name: SourceCode
    - Name: BuildTASHydroRateCardLambdaOutput
    - Name: BuildTASHydroCreateBucketLambdaOutput
    - Name: BuildTASHydroPartitionLambdaOutput
  Configuration:
    ActionMode: REPLACE_ON_FAILURE
    RoleArn: !GetAtt [CFNRole, Arn]
    StackName: !Ref TestStackName
    Capabilities: CAPABILITY_NAMED_IAM
    TemplateConfiguration: !Sub "SourceCode::cloudformation/config/${TestStackConfig}"
    TemplatePath: "SourceCode::cloudformation/lambda.cfn.yaml"
    ParameterOverrides: !Sub |
      {
        "SourceLocation" : { "Fn::GetArtifactAtt" : ["SourceCode", "URL"] },
        "TASHydroRateCardLocation" : { "Fn::GetArtifactAtt" : ["BuildTASHydroRateCardLambdaOutput", "URL"] },
        "TASHydroRateCardKey" : { "Fn::GetArtifactAtt" : ["BuildTASHydroRateCardLambdaOutput", "ObjectKey"] },
        "TASHydroPartitionLocation" : { "Fn::GetArtifactAtt" : ["BuildTASHydroPartitionLambdaOutput", "URL"] },
        "TASHydroPartitionKey" : { "Fn::GetArtifactAtt" : ["BuildTASHydroPartitionLambdaOutput", "ObjectKey"] },
        "TASHydroCreateBucketLocation" : { "Fn::GetArtifactAtt" : ["BuildTASHydroCreateBucketLambdaOutput", "URL"] },
        "TASHydroCreateBucketKey" : { "Fn::GetArtifactAtt" : ["BuildTASHydroCreateBucketLambdaOutput", "ObjectKey"] }
      }
  RunOrder: '1'
```
The first stage in the pipeline runs a cloudformation task, but instead of the cloudformation stack being defined inline, this task references another cloudformation template `lambda.cfn.yaml` which is responsible for deploying the lambdas built earlier in the codepipeline and the dependencies that these lambdas rely on.  To access the source code retrieved from git earlier and the built lambdas, this cloudformation stack needs to have the references to these artifacts passed to it.  This is achieved via the `InputArtifacts` section and the `ParameterOverrides` section.

```
- Name: ApproveTestStack
  ActionTypeId:
    Category: Approval
    Owner: AWS
    Provider: Manual
    Version: '1'
  Configuration:
    NotificationArn: !Ref CodePipelineSNSTopic
    CustomData: !Sub 'Do you want to create a changeset against the production stack and delete the test stack?'
  RunOrder: '2'
```
To progress to deploying to production, a user has to manually approve that the code running in the test stack is good.  The approval is done via clicking a button in the code pipeline and entering a comment.  This prevents the scenario of accidentally deploying broken code as the developer can check that the code behaves as expected by uploading files into the test S3 buckets and seeing them being processed correctly.

The next stage deletes any test files that were added to the test buckets etc.
```
- Name: CleanupTestFiles
  ActionTypeId:
    Category: Deploy
    Owner: AWS
    Provider: CloudFormation
    Version: '1'
  InputArtifacts:
    - Name: SourceCode
    - Name: BuildTASHydroDeleteTestFilesLambdaOutput
  Configuration:
    ActionMode: REPLACE_ON_FAILURE
    RoleArn: !GetAtt [CFNRole, Arn]
    StackName: !Ref CleanupStackName
    Capabilities: CAPABILITY_NAMED_IAM
    TemplateConfiguration: !Sub "SourceCode::cloudformation/config/${TestStackConfig}"
    TemplatePath: "SourceCode::cloudformation/clean-test-files-lambda.cfn.yaml"
    ParameterOverrides: !Sub |
      {
        "SourceLocation" : { "Fn::GetArtifactAtt" : ["SourceCode", "URL"] },
        "TASHydroDeleteTestFilesLocation" : { "Fn::GetArtifactAtt" : ["BuildTASHydroDeleteTestFilesLambdaOutput", "URL"] },
        "TASHydroDeleteTestFilesKey" : { "Fn::GetArtifactAtt" : ["BuildTASHydroDeleteTestFilesLambdaOutput", "ObjectKey"] }
      }
  RunOrder: '4'
```
Next the test stack is deleted.
```
Name: DeleteTestStack
  ActionTypeId:
    Category: Deploy
    Owner: AWS
    Provider: CloudFormation
    Version: '1'
  Configuration:
    ActionMode: DELETE_ONLY
    RoleArn: !GetAtt [CFNRole, Arn]
    StackName: !Ref TestStackName
  RunOrder: '4'
```
After a user has approved the deployment, the test stack is deleted before the prod stack is created.

#### Note: Deleting S3 buckets
If during testing, a file was uploaded to a testing S3 bucket and was not removed before the `ApproveTestStack` is clicked, then the `DeleteTestStack` will fail to execute and the deployment will not progress to production.

### Stage 4: ProdStage
The `ProdStage` is similar to the `TestStage`, except it creates a changeset that it applies to the currently running production stack.  This changeset captures all the differences in code and infrastructure between versions and allows the user to rollback to a prior version and know that it has reverted both the code and any infrastructure changes.

#### Note: Change Sets
Unlike the `TestStage`, changes to the `ProdStage` are applied via an aws changeset https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-updating-stacks-changesets.html this is because the `TestStage` is recreated from scratch each time, unlike the `ProdStage` which needs to have changes captured in a fashion that allows them to be rolled back safely should they be incomplete or incorrect.
