## 무엇을 바꿨나요?

바꾼 내용과 사용자가 느끼는 차이를 짧게 적어 주세요.

## 기여자가 확인할 것

- [ ] `uv sync --locked --python 3.13`
- [ ] `uv run --locked python scripts/verify-direct-release-tree.py`
- [ ] `uv run --locked python test/run_tests.py fast`
- [ ] 동작을 바꿨다면 관련 테스트를 추가했습니다
- [ ] wrapper를 바꿨다면 shell 또는 PowerShell 문법을 확인했습니다

## 공개해도 되는 파일인가요?

- [ ] 새 배포 파일을 만들었다면 공개 경계 검증을 함께 갱신했습니다
- [ ] 책, PDF, 책에서 꺼낸 내용, 새 데이터와 새 음성을 넣지 않았습니다
- [ ] 덱, release ZIP, 로컬 DB, 비밀번호, 토큰, 개인 경로를 넣지 않았습니다
- [ ] 코드·문서·사이트는 AGPL-3.0-or-later이며, `NOTICE`의 별도 조건도 확인했습니다

## Maintainer가 merge 또는 release 전에 확인할 것

- [ ] 실제 코어 분리 결과로 `config/public-release.json`을 갱신했거나, pin 갱신이 필요 없습니다
- [ ] `uv run --locked python scripts/verify-direct-release-tree.py`가 통과했습니다
- [ ] 정식 release라면 코어 import와 길벗 PDF 2개 한자 빌드·합산 import를 확인했습니다
