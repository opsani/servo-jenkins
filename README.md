# servo-jenkins

Optune servo driver to trigger a Jenkins Pipeline stage as load generator

## Supported environment variables

* `JENKINS_URL` - URL to the Jenkins pipeline/stage for load
* `JENKINS_SECRET_PATH` - File path to the Jenkins access Token (default /etc/opsani/jenkins/token)
* `JENKINS_TOKEN` - Alternate way to provide a Jenkins Token
* `JENKINS_USER` - User for Jenkins Token based access
