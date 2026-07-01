pipeline {
    agent any

    stages {
        stage('Checkout') {
            steps {
                echo '代码已从 GitHub 拉取'
            }
        }

        stage('Build Site') {
            steps {
                sh '''
                    pip3 install markdown 2>/dev/null || apt install -y python3-markdown
                    python3 build_site.py
                '''
            }
        }

        stage('Deploy') {
            steps {
                sh '''
                    TARGET=/var/www/drone-ai-wiki

                    # 备份数据库
                    mkdir -p $TARGET/backups
                    cp $TARGET/server/data/annotations.db $TARGET/backups/annotations-$(date +%F-%H%M%S).db 2>/dev/null || echo "（数据库不存在，跳过备份）"

                    # 上传 site 和 assets
                    rsync -av --delete site/ $TARGET/site/
                    rsync -av assets/ $TARGET/assets/

                    # 修权限
                    chmod -R 755 $TARGET/site $TARGET/assets

                    # 重载 Nginx
                    systemctl reload nginx 2>/dev/null || echo "Nginx 重载失败，请检查"
                '''
            }
        }
    }

    post {
        success {
            echo '✅ 部署成功！'
        }
        failure {
            echo '❌ 部署失败，请检查日志'
        }
    }
}
