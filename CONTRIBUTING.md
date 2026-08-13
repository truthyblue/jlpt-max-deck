# 기여하기

도와주셔서 감사합니다. 이 저장소에는 공개해도 되는 코드와 문서만 둡니다.

## 먼저 준비하기

저장소를 받은 뒤 아래 명령을 먼저 실행합니다.

```console
uv sync --locked --python 3.13
```

그다음 기여자용 검사와 빠른 테스트를 실행합니다.

```console
uv run --locked python scripts/verify-direct-release-tree.py
uv run --locked python test/run_tests.py fast
```

이 검사는 `config/public-release.json`의 형식·자체 해시, 한자 빌더의 공개
source 목록과 저장소에 APKG·PDF·ZIP이 추적되지 않는 경계를 확인합니다.
선택형 한자 빌더 ZIP의 source 목록은
`src/direct_release_contract.py`의 `KANJI_BUILDER_FILES` 한 곳에서 관리합니다.

Windows의 줄바꿈은 `.gitattributes`가 정합니다. 검사 전에 파일을 따로 바꾸지 마세요.

## 문서와 사이트 수정

README, `docs/anki.md`, `docs/build.md`, `docs/privacy-and-licensing.md`,
`docs/releases/*.md`, `docs/troubleshooting.md`, `site/*.html`은 생성 결과입니다.
직접 고치지 말고 `docs-src/`의 Jinja 템플릿과
`docs-src/data/product.json`을 수정합니다.

```console
uv run --locked python scripts/render-docs.py --write
uv run --locked python scripts/render-docs.py --check
```

학습자용 문서에서는 **기본 덱**과 **선택형 한자 확장**이라는 이름을 사용합니다.
`core`, skeleton, pin, source hash 같은 내부 용어는 파일명이나 maintainer 계약을
설명할 때만 사용하세요. 외부 링크와 수량·해시는 현재 Release와 대조합니다.

`docs/kanji-builder.md`, `LICENSE`, `NOTICE`는 한자 빌더 ZIP에 들어가는
release-bound source입니다. 이 파일을 바꾸면 builder source hash와 Release 자산을
함께 갱신해야 하므로 일반 문서 수정에 포함하지 않습니다.

### 갤러리 공지 미리보기

릴리스별 갤러리 이미지는 `site/assets/releases/vX.Y.Z/` 아래에 보관합니다.
갤러리 공지 원본은 게시 후에도 동작하는 Pages 절대 URL을 사용하므로, 배포 전에는
원본 HTML을 `file://`로 직접 열지 말고 로컬 미리보기를 생성합니다.

```console
uv run --locked python scripts/render_gallery_preview.py 1.2.0
```

생성된 `build/gallery-preview/v1.2.0.html`은 같은 저장소의 로컬 이미지를 사용합니다.
함께 생성되는 receipt에는 공지 원본과 미리보기, 사용한 모든 이미지의 SHA-256이
기록됩니다. 릴리스 승인 전에는 이 미리보기를 실제 브라우저에서 열어 모든 이미지가
로드되는지 확인합니다.

## 넣을 수 없는 것

다음 자료는 pull request로 받지 않습니다.

- 책과 PDF, 책에서 꺼낸 글이나 그림
- 새 데이터와 새 음성 파일
- 만들어진 덱, release ZIP, 로컬 데이터베이스 (공식 Release asset은 maintainer가 별도 업로드)
- 비밀번호, 토큰, 개인 PC 경로
- 비공개 제작 기록과 검토 자료

## 변경을 작게 만들기

- 동작을 바꾸면 작은 가짜 입력을 쓰는 테스트도 추가합니다.
- 빌드는 같은 입력에서 항상 같은 결과를 내야 합니다.
- 빌드 중에는 인터넷 서비스를 부르지 않습니다.
- 새 dependency는 꼭 필요할 때만 추가합니다.
- commit 제목은 짧은 명령문으로 씁니다.

## Maintainer가 하는 최종 검사

기여자는 기본 덱 APKG나 출판사 PDF를 가지고 있지 않아도 됩니다. Maintainer는
release 전에 검증된 전체 APKG를 기본 덱·한자 골격으로 분리해 새 pin을 만들고
검사를 실행합니다.

```console
uv run --locked python scripts/verify-direct-release-tree.py
```

정식 release를 만들 때는 maintainer가 기본 덱 APKG를 새 컬렉션에 가져오고, 길벗 PDF
2개로 한자 확장 덱을 만든 뒤 두 APKG의 합산 import와 SQLite 무결성을 확인합니다.
PDF와 APKG는 저장소나 CI에 커밋하지 않고 GitHub Release asset으로만 다룹니다.

## 라이선스

코드, 문서, 사이트 기여는 `LICENSE`의 AGPL-3.0-or-later 조건으로 받습니다. 다만
`NOTICE`가 특정 파일이나 자료에 다른 조건을 적었다면 그 조건을 따릅니다. 이 저장소는
새 데이터와 새 음성 기여를 받지 않습니다.
