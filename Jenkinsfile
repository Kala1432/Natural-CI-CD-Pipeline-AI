pipeline {
    agent any

    triggers {
        githubPush()
    }

    environment {
        PATH = "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
        IMAGE_NAME = "niku1432/natural-ci-cd:latest"
        EC2_HOST = "13.51.172.247"
    }

    stages {

        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Build Docker Image') {
            steps {
                sh 'docker build -t $IMAGE_NAME .'
            }
        }

        stage('Login to Docker Hub') {
            steps {
                withCredentials([usernamePassword(
                    credentialsId: 'docker-cred',
                    usernameVariable: 'DOCKER_USER',
                    passwordVariable: 'DOCKER_PASS'
                )]) {
                    sh '''
                    echo $DOCKER_PASS | docker login -u $DOCKER_USER --password-stdin
                    '''
                }
            }
        }

        stage('Push Docker Image') {
            steps {
                sh 'docker push $IMAGE_NAME'
            }
        }

        stage('Deploy to EC2') {
            steps {
                sshagent(credentials: ['ubuntu-1']) {
                    sh """
                    ssh -o StrictHostKeyChecking=no ubuntu@${EC2_HOST} '
                    docker network create pipeline-network || true
                    docker volume create pipeline-mongodb-data || true
                    docker rm -f mongo || true
                    docker run -d --name mongo --restart unless-stopped --network pipeline-network -v pipeline-mongodb-data:/data/db mongo:6
                    sleep 5
                    docker pull ${IMAGE_NAME}
                    docker stop web || true
                    docker rm web || true
                    docker run -d -p 8080:5000 --name web --restart unless-stopped --network pipeline-network -e MONGODB_URI=mongodb://mongo:27017/pipeline_sh ${IMAGE_NAME}
                    '
                    """
                }
            }
        }
    }

    post {
        always {
            sh 'docker logout || true'
        }
        success {
            echo "Deployment Successful"
        }
        failure {
            echo "Deployment Failed"
        }
    }
}
