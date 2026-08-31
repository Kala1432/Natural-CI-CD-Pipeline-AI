import { useMemo, useState } from "react"

const DEFAULT_JENKINSFILE = `pipeline {
    agent any

    environment {
        IMAGE_NAME = "DOCKERHUB_USERNAME/IMAGE_NAME:IMAGE_TAG"
        EC2_HOST = "EC2_PUBLIC_IP_OR_DNS"
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
                    ssh -o StrictHostKeyChecking=no ubuntu@\${EC2_HOST} '
                    docker pull \${IMAGE_NAME}
                    docker stop web || true
                    docker rm web || true
                    docker run -d -p 80:80 --name web \${IMAGE_NAME}
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
}`

const JenkinsSetup = () => {
  const [dockerUsername, setDockerUsername] = useState("")
  const [imageName, setImageName] = useState("web")
  const [imageTag, setImageTag] = useState("latest")
  const [ec2Host, setEc2Host] = useState("")
  const [sshUser, setSshUser] = useState("ubuntu")
  const [dockerCredentialId, setDockerCredentialId] = useState("docker-cred")
  const [sshCredentialId, setSshCredentialId] = useState("ubuntu-1")
  const [copied, setCopied] = useState(false)

  const jenkinsfile = useMemo(() => DEFAULT_JENKINSFILE
    .replace("DOCKERHUB_USERNAME/IMAGE_NAME:IMAGE_TAG", `${dockerUsername || "DOCKERHUB_USERNAME"}/${imageName || "IMAGE_NAME"}:${imageTag || "IMAGE_TAG"}`)
    .replace('EC2_PUBLIC_IP_OR_DNS', ec2Host || "EC2_PUBLIC_IP_OR_DNS")
    .replaceAll("docker-cred", dockerCredentialId || "docker-cred")
    .replaceAll("ubuntu-1", sshCredentialId || "ubuntu-1")
    .replaceAll("ubuntu@${EC2_HOST}", `${sshUser || "ubuntu"}@${EC2_HOST}`),
    [dockerUsername, imageName, imageTag, ec2Host, sshUser, dockerCredentialId, sshCredentialId])

  const copyJenkinsfile = async () => {
    await navigator.clipboard.writeText(jenkinsfile)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1800)
  }

  const downloadJenkinsfile = () => {
    const blob = new Blob([jenkinsfile], { type: "text/plain" })
    const url = URL.createObjectURL(blob)
    const link = document.createElement("a")
    link.href = url
    link.download = "Jenkinsfile"
    link.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-indigo-400">Deployment automation</p>
        <h1 className="mt-2 text-2xl font-semibold text-white">Jenkins setup</h1>
        <p className="mt-2 max-w-2xl text-sm text-slate-400">Prepare a Jenkinsfile for Docker Hub and an EC2 deployment without sending secrets to this app.</p>
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)]">
        <section className="rounded-xl border border-subtle bg-[#111827] p-6">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-400">Deployment values</h2>
          <p className="mt-2 text-xs leading-5 text-slate-500">Only non-secret values are used to customize the file. Enter the Docker password and EC2 private key directly into Jenkins credentials.</p>
          <div className="mt-6 space-y-4">
            <Field label="Docker Hub username" value={dockerUsername} onChange={setDockerUsername} placeholder="your-docker-user" />
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Image name" value={imageName} onChange={setImageName} placeholder="web" />
              <Field label="Image tag" value={imageTag} onChange={setImageTag} placeholder="latest" />
            </div>
            <Field label="EC2 public IP or DNS" value={ec2Host} onChange={setEc2Host} placeholder="ec2-12-34-56-78.compute.amazonaws.com" />
            <Field label="EC2 SSH username" value={sshUser} onChange={setSshUser} placeholder="ubuntu" />
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Docker credential ID" value={dockerCredentialId} onChange={setDockerCredentialId} placeholder="docker-cred" />
              <Field label="SSH key credential ID" value={sshCredentialId} onChange={setSshCredentialId} placeholder="ubuntu-1" />
            </div>
          </div>
          <div className="mt-6 border-t border-white/10 pt-5">
            <h3 className="text-sm font-medium text-white">Create these Jenkins credentials</h3>
            <ul className="mt-3 space-y-2 text-xs leading-5 text-slate-400">
              <li><span className="font-medium text-slate-200">{dockerCredentialId || "docker-cred"}</span>: Username with password or access token for Docker Hub.</li>
              <li><span className="font-medium text-slate-200">{sshCredentialId || "ubuntu-1"}</span>: SSH username with private key for the EC2 instance.</li>
            </ul>
          </div>
        </section>

        <section className="rounded-xl border border-subtle bg-[#0b1120] p-6">
          <div className="flex items-center justify-between gap-4">
            <div>
              <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-400">Generated Jenkinsfile</h2>
              <p className="mt-1 text-xs text-slate-500">Secrets remain referenced by Jenkins credential IDs.</p>
            </div>
            <div className="flex gap-2">
              <button type="button" onClick={copyJenkinsfile} className="rounded-lg border border-white/10 px-3 py-2 text-xs font-semibold text-slate-300 hover:bg-white/5">{copied ? "Copied" : "Copy"}</button>
              <button type="button" onClick={downloadJenkinsfile} className="rounded-lg bg-indigo-600 px-3 py-2 text-xs font-semibold text-white hover:bg-indigo-500">Download</button>
            </div>
          </div>
          <pre className="mt-5 max-h-[680px] overflow-auto rounded-lg border border-white/10 bg-black/20 p-4 text-xs leading-5 text-slate-300">{jenkinsfile}</pre>
        </section>
      </div>
    </div>
  )
}

const Field = ({ label, value, onChange, placeholder }) => (
  <label className="block">
    <span className="mb-1.5 block text-sm font-medium text-slate-300">{label}</span>
    <input value={value} onChange={(event) => onChange(event.target.value)} placeholder={placeholder} className="w-full rounded-lg border border-white/10 bg-white/5 px-3.5 py-2.5 text-sm text-white placeholder-slate-600 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500" />
  </label>
)

export default JenkinsSetup
