#!/bin/zsh
# Double-click from Finder to publish the prepared checkout with its ignored .env.local.
set -u
cd -- "$(dirname -- "$0")/.." || exit 1

# Use the supported Node version already installed on this computer, when available.
deploy_node_bin="$HOME/.nvm/versions/node/v22.22.0/bin"
if [[ -x "$deploy_node_bin/node" ]]; then
  export PATH="$deploy_node_bin:$PATH"
fi

make deploy-openai
deploy_status=$?
printf '\n'
if [[ $deploy_status -eq 0 ]]; then
  printf '배포 완료. https://natural-language-brain-alpha-harness.vercel.app 에서 테스트하세요.\n'
else
  printf '배포가 완료되지 않았습니다. 위 오류 메시지를 확인하세요.\n'
fi
printf '창을 닫으려면 Enter를 누르세요. '
read -r deploy_close
exit "$deploy_status"
