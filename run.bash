# 環境変数 BUCKET_NAME に log.txt を作成し、１０秒に１回現在時刻を書き込む

set -eux

# BUCKET_NAMEが定義されているかチェック
if [ -z "${BUCKET_NAME}" ]; then
  echo "BUCKET_NAME is not defined"
  exit 1
fi

# mountpoint s3を導入
curl https://s3.amazonaws.com/mountpoint-s3-release/latest/x86_64/mount-s3.rpm -o mount-s3.rpm
yum install -y ./mount-s3.rpm

# マウント
mkdir ./bucket ./cache-bucket
mount-s3 "${BUCKET_NAME}" ./bucket --cache ./cache-bucket --allow-delete

ls ./bucket

# ファイルがあれば持ってくる
if [ -e ./bucket/log.txt ]; then
  cp ./bucket/log.txt /tmp/log.txt
fi

# log.txtを読み込んで、最後に現在時刻を追記し、保存する
# mountpointは追記ができないので一度ファイルを読み込んで保存する
while true; do
  date >>/tmp/log.txt
  rm -f ./bucket/log.txt
  cp /tmp/log.txt ./bucket/log.txt
  sleep 10
done
