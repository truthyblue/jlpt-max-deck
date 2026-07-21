# 기여하기

도와주셔서 감사합니다. 이 저장소에는 공개해도 되는 코드와 문서만 둡니다.

## 먼저 준비하기

저장소를 받은 뒤 아래 명령을 먼저 실행합니다.

```console
uv sync --locked --python 3.13
```

그다음 기여자용 검사와 빠른 테스트를 실행합니다.

```console
uv run --locked python scripts/verify-public-tree.py --allow-release-pin-drift
uv run --locked python test/run_tests.py fast
```

`--allow-release-pin-drift`는 한 가지만 허용합니다. 수정한 빌더 코드의 해시가 현재
릴리스 pin과 달라도 기여자 검사를 계속할 수 있습니다. 다음 검사는 그대로 엄격하게
실행됩니다.

- `config/public-release.json`의 형식, 상태, 자체 해시
- 공개 파일 목록과 runtime 파일 목록
- 비공개 이름, 개인 경로, 금지된 파일과 폴더
- 공개 PDF 목록과 layout 계약

새 파일을 만들었다면 `config/public-source-files.txt`에도 추가합니다.
`config/public-runtime-files.txt`는 실제 빌더에 들어가는 작은 파일 목록입니다. 이 목록은
`src/public_build_contract.py`의 `PUBLIC_BUILD_FILES`와 정확히 같아야 합니다.

Windows의 줄바꿈은 `.gitattributes`가 정합니다. 검사 전에 파일을 따로 바꾸지 마세요.

## 넣을 수 없는 것

다음 자료는 pull request로 받지 않습니다.

- 책과 PDF, 책에서 꺼낸 글이나 그림
- 새 데이터와 새 음성 파일
- 만들어진 덱, release ZIP, 로컬 데이터베이스
- 비밀번호, 토큰, 개인 PC 경로
- 비공개 제작 기록과 검토 자료

## 변경을 작게 만들기

- 동작을 바꾸면 작은 가짜 입력을 쓰는 테스트도 추가합니다.
- 빌드는 같은 입력에서 항상 같은 결과를 내야 합니다.
- 빌드 중에는 인터넷 서비스를 부르지 않습니다.
- 새 dependency는 꼭 필요할 때만 추가합니다.
- commit 제목은 짧은 명령문으로 씁니다.

## Maintainer가 하는 최종 검사

기여자는 release 파일이나 출판사 PDF를 가지고 있지 않아도 됩니다. Maintainer는 merge와
release 전에 새 bundle로 pin을 만들고 아래의 엄격한 검사를 실행합니다.

```console
uv run --locked python scripts/verify-public-tree.py
```

이 명령에는 `--allow-release-pin-drift`를 붙이지 않습니다. 빌더 코드와
`config/public-release.json`의 해시가 정확히 같아야 합니다. Pull request CI는 기여자
모드로 검사하고, `main`에 들어간 코드와 release는 이 엄격한 모드로 검사합니다.

정식 release를 만들 때는 maintainer가 실제 PDF 17개로 전체 빌드를 확인하고,
성공한 운영체제와 결과값을 릴리스 노트에 적습니다. 확인하지 못한 운영체제도
숨기지 않고 적습니다. PDF는 저장소와 CI에 올리지 않습니다.

## 라이선스

코드, 문서, 사이트 기여는 `LICENSE`의 AGPL-3.0-or-later 조건으로 받습니다. 다만
`NOTICE`가 특정 파일이나 자료에 다른 조건을 적었다면 그 조건을 따릅니다. 이 저장소는
새 데이터와 새 음성 기여를 받지 않습니다.
