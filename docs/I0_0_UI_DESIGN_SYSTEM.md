# i0_0 UI Design System

> **Canonical UI Reference**
> 현재 `i0_0`의 **SCREEN-02 실행 화면**을 Workspace Component Design의 단일 Canonical UI Reference로 선언한다. 화면별 업무 구성과 Grid는 달라질 수 있지만, 같은 역할의 card, field, control, action, icon, guidance, feedback surface는 SCREEN-02에서 확정한 동일한 시각 계약을 사용한다. Global Shell과 Agent Dock은 Workspace component와 계층이 다른 Shell Component Family로 유지한다.

## 1. 기준과 적용 범위

- Workspace Component Standard의 Source of Truth: `request_ai_agent_i0_0/ui.py`의 현재 SCREEN-02 구현.
- Foundation과 Shell의 Source of Truth: `request_ai_agent_i0_0/ui.py`의 후반 I0_0 override가 반영된 현재 구현.
- 이 문서는 현재 구현값과 목표 표준을 구분한다. SCREEN-02와 다른 현재 화면의 값은 표준의 근거가 아니라 migration 대상이다.
- 과거 h7 UI, Blue-Gray 디자인, mockup, 이전 지시와 현재 코드가 다르면 현재 `ui.py`를 우선한다.
- 기준 소스 SHA-256: `6CFDAD95138E5380D4F7105614F9BC6A78789F9C4F407180B609427DBAC937A2`.
- 아래 값은 CSS cascade의 후반 I0_0 override까지 반영한 값이다. 반응형 분기가 있는 항목은 별도로 표시한다.

## 2. Design Foundation

### 2.1 Font

공통 font stack은 다음과 같다.

```css
"Noto Sans KR","Malgun Gothic","Segoe UI",sans-serif
```

`body`에 이 stack이 선언되고 `button`, `input`, `textarea`, `select`는 `font-family:inherit`를 사용한다. `.workspace-shell`은 같은 값을 `--request-workspace-font`로 다시 연결하며, Workspace form에도 이를 명시한다. `.prep-head p` 역시 동일한 stack을 직접 선언한다. 따라서 Body, Workspace, Agent, Button, Input, Select, Textarea는 모두 같은 font 계열을 사용한다.

### 2.2 Root color tokens

| Token | 값 | 현재 용도 |
|---|---:|---|
| `--ink` | `#202124` | 기본 text, 주요 heading/value |
| `--muted` | `#76797D` | caption, label, secondary text, 비활성 navigation |
| `--bg` | `#F8F8F8` | page background와 footer background |
| `--paper` | `#FFFFFF` | main surface, card, control, Agent surface |
| `--soft` | `#FAFAFA` | subtle surface, hover 또는 보조 영역 |
| `--line` | `#E0E1E2` | 일반 border와 shell 경계 |
| `--line-strong` | `#D4D5D6` | control, 정보 surface, 강조 경계 |
| `--brand` | `#5A5A5A` | 일부 selected state와 resizer hover |
| `--brand-strong` | `#545454` | primary action, active navigation, CAE mark |
| `--accent` | `#545454` | focus/navigation/workspace accent alias |
| `--disabled-bg` | `#F2F2F2` | disabled control background |
| `--disabled-text` | `#A8AAAC` | disabled control text |

현재 root에는 다음 중립 semantic alias도 존재한다: `--danger:#4a4a4a`, `--warning:#5c5c5c`, `--ok:#4a4a4a`, `--blue:#5c5c5c`. 이름과 달리 모두 현재 neutral UI 계열이며, 새 화면에서 임의의 의미 색상으로 확장하는 근거로 사용하지 않는다. 실제 누락/오류 표시에 국소적으로 쓰이는 `#c62828` 등은 neutral foundation과 별도의 semantic color다.

### 2.3 Spacing

Root spacing scale은 다음과 같다.

| Token | 값 |
|---|---:|
| `--space-1` | `4px` |
| `--space-2` | `8px` |
| `--space-3` | `12px` |
| `--space-4` | `16px` |
| `--space-5` | `20px` |
| `--space-6` | `24px` |
| `--space-8` | `32px` |

이 scale을 이후 화면 확장의 기본 간격 기준으로 사용한다. SCREEN-02의 canonical component inset은 `16px`, field label과 control 사이는 `6px`, standard form grid gap은 `12px`다. Compact/Data Grid는 열 구성과 행 밀도에 한해 `8~10px` gap을 사용할 수 있지만 component 내부 간격을 임의 변경하는 근거가 되지 않는다.

### 2.4 Radius

| 계층 | 현재 대표 selector | 값 |
|---|---|---:|
| Form control / Button | `input, textarea, select`, `button` | `8px` |
| Standard Workspace Group Card | SCREEN-02 `.section` | `10px` |
| Summary inner surface | `.prep-summary-values` | `8px` |
| 의뢰 제목/번호 card | `.workspace-title-summary`, `.workspace-number-block` | `10px` |
| 6-Step navigation shell | `.screen-map` | `11px` |
| Main Workspace / Agent 주요 panel | `.panel`, `.main`, `.workspace`, `.agent-dock` | `12px` |
| Agent message | `.msg` | `9px` |

### 2.5 Shadow

```css
--shadow: 0 3px 14px rgba(0,0,0,.05);
--shadow-soft: 0 1px 4px rgba(0,0,0,.035);
```

`--shadow`는 Global shell의 의뢰 제목/번호 card, 6-Step navigation, Main Workspace, Agent Dock에 사용한다. SCREEN-02를 기준으로 Workspace 내부의 Standard Group Card에는 shadow를 사용하지 않고 border와 whitespace로 계층을 만든다. `--shadow-soft`는 root에 정의되어 있지만 현재 `ui.py`에서 실제 `var(--shadow-soft)` 참조는 없다.

### 2.6 Focus와 Disabled

- 공통 focus-visible: `button`, `input`, `textarea`, `select`, `[tabindex]`에 `border-color:#8E9092`, `outline:3px solid rgba(84,84,84,.16)`, `outline-offset:1px`를 적용한다.
- Workspace form의 `input/select/textarea`도 같은 focus 표현을 명시한다.
- Navigation focus는 같은 outline 구조에서 accent 색을 사용한다. `.screen-map-item:focus-visible`은 내부 방향형 surface에 맞춰 `outline-offset:-3px`를 사용한다.
- 공통 disabled button은 `--line` border, `--disabled-bg`, `--disabled-text`, `cursor:not-allowed`를 사용한다.
- Disabled select는 `--disabled-bg`와 `--disabled-text`를 사용한다.
- Locked navigation은 native `:disabled`가 아니라 `[aria-disabled="true"]`다. surface는 유지하고 number/label에 muted color와 `opacity:.55`를 적용하며 lock icon을 표시한다.
- 이 문서는 현재 CSS만 기록한다. 현재 구현에 없는 추가 accessibility 상태나 색상 규칙은 정의하지 않는다.

## 3. Typography Roles

명시되지 않은 line-height는 임의 수치로 보완하지 않고 “미지정”으로 표기한다. 일반 text는 별도 override가 없으면 `body`의 `line-height:1.6`을 상속한다.

| Role | 대표 selector | Size | Weight | Line-height | Color |
|---|---|---:|---:|---:|---|
| App Title | `h1` | `18px` | `600` | `1.2` | `--ink` 상속 |
| Screen Heading | `.screen-heading` + `.screen-heading span` | `24px` | `600` | `1.3` | text `--ink`, heading container `--muted` |
| Screen Description | `.screen-description` | `13px` | `400` | `1.35` | `--muted` |
| Group / Card Title | SCREEN-02 `.section-head h3` | `16px` | `600` | `1.6` 상속 | `--ink` |
| Summary Title | `.prep-summary > strong` | `15px` | `600` | `1.5` 상속 | `--ink` |
| Field Label / Column Header | SCREEN-02 label, SCREEN-03 table header | `13px` | `500` | `1.45` | `--ink` |
| Input / Select Value | SCREEN-02 `input, select` | `14px` | `400` | `1.45` | `--ink` |
| Body | `body` | `14px` | `400` | `1.6` | `--ink` |
| Emphasized Body | `.prep-guidance-line:first-child` | `15px` | `600` | `1.55` | `--ink` |
| Caption / Helper | `.prep-guidance-next` | `13px` | `400` | `1.55` | `#55585B` |
| Button | `button` | `14px` | `500` | 미지정 | `--ink` |
| Primary CTA | `.prep-summary-actions .primary` | `15px` | `600` | 미지정 | `#FFFFFF` |
| Navigation Number | `.screen-map-number` | `26px` | `600` | `1` | state에 따라 `--muted` 또는 white |
| Navigation Label | `.screen-map-label` | `12px` | `500` | `1.25` | state에 따라 `--muted` 또는 white |
| Agent Heading | `.stage-assist-title` | `18px` | `600` | `1.6` 상속 | `#151617` |
| Agent Message | `.msg` | `14px` | `400` | `1.65` | `--ink` 상속 |

SCREEN-02의 heading은 `24px/600/1.3`, `margin-bottom:8px`, `padding:3px 0`, letter-spacing `-0.02em`이다. SCREEN-03~06도 같은 canonical heading 계약을 사용한다.

## 4. Global Shell Components

| Component | 주요 selector | 역할과 현재 시각 특성 |
|---|---|---|
| Global Header | `.topbar[data-shell="GlobalHeader"]` | 높이 `72px`, padding `12px 24px`, paper surface, 하단 `--line` border, shadow 없음 |
| CAE Brand Mark | `.brand-mark` | `40×40px`, radius `8px`, `--brand-strong`, white `12px/700` text |
| 새 의뢰 시작 Button | `#newRequestBtn.primary`, `.top-actions .primary` | 최소 높이 `40px`, padding `9px 16px`, radius `8px`, charcoal primary surface |
| 의뢰 제목 Card | `.workspace-title-summary` | 최소 높이 `88px`, padding `15px 18px`, `--line` border, radius `10px`, paper, `--shadow`; label `12px/500`, title `16px/600` |
| 의뢰 번호 Card | `.workspace-number-block` | 제목 card와 같은 surface; value `15px/600` |
| 6-Step Navigation | `.step-navigation`, `.screen-map`, `.screen-map-item` | 6열 chevron hierarchy, shell 최소 높이 `82px`, `--line` border, radius `11px`, paper, `--shadow` |
| Active Navigation | `.screen-map-item[aria-current="page"]` | `--brand-strong` background, white text, `z-index:2` |
| Locked Navigation | `.screen-map-item[aria-disabled="true"]` | 기존 paper surface 유지, muted text `opacity:.55`, leading lock icon, not-allowed cursor |
| Main Workspace | `.panel.main[data-shell="MainWorkspaceContent"]`, `.workspace` | `--line` border, radius `12px`, paper, `--shadow`; 데스크톱 workspace padding `10px 18px` |
| Panel Resizer | `#panelResizer.panel-resizer` | 데스크톱 container 폭 `22px`; 기본 선 `1×46px`, `#d4d5d5`; hover/drag `3×72px`, `--brand` |
| Agent Dock | `#agentDock.agent-dock` | Main Workspace와 독립된 paper panel, `--line` border, radius `12px`, `--shadow` |
| Agent Header | `.chat-head` | padding `16px 18px`, `#F7F7F7`, 하단 `--line-strong` border; icon surface `28px`, radius `8px` |
| Agent Message | `.msg`, `.msg.assistant`, `.msg.user` | 최대 폭 `100%`, padding `11px 12px`, radius `9px`; assistant paper + line, user `#f1f1f0` |
| Chat Input | `.chat-input`, `.chat-row textarea`, `.chat-row .primary` | paper surface, 상단 `--line`, padding `14px`; textarea 높이 `50px`, send button 최소 `64×50px` |
| Footer | `.app-footer` | 최소 높이 `44px`, page background, muted `12px/1.5`; link 사이 `--line-strong` 구분선 |

데스크톱(`min-width:1040px`)의 기본 layout 비율은 Workspace `2.285fr`, resizer `16px`, Agent `1fr`이다. `max-width:1039px`에서는 Agent Dock이 fixed overlay로 전환된다. 이 반응형 동작도 현재 Shell 계약의 일부다.

## 5. SCREEN-02 Canonical Component Standard

이 절은 현재 화면별 selector 이름이 아니라 **사용자에게 보이는 역할**을 기준으로 적용한다. 같은 역할의 component는 어느 SCREEN에서 사용되더라도 typography, surface, border, radius, padding, icon, interaction state가 같아야 한다.

### Screen Heading — `.screen-heading`

각 SCREEN의 최상위 업무 제목이다. SCREEN-02 기준 `24px/600/1.3`, letter-spacing `-0.02em`, margin-bottom `8px`, padding `3px 0`이며 text는 `--ink`이고 아이콘 없이 사용한다. 내부 `.screen-heading-code`는 Workspace에서 숨긴다.

### Screen Description — `.screen-description`

Screen Heading 아래의 설명은 `margin:0 0 7px`, `13px/400/1.35`, muted text를 사용한다. 설명 내부의 제한적인 `<strong>` 강조는 허용하지만 별도 색상이나 크기를 만들지 않는다.

### Guidance / Info Surface — `.prep-head`, `.geometry-policy-guidance`

업무 진행에 필요한 핵심 안내 surface다. `display:flex`, gap `12px`, 최소 높이 `86px`, padding `16px`, `--line-strong` border, radius `10px`, `#F7F7F7`, shadow 없음이다. 안내 제목은 `15px/600/1.55`, 본문은 `13px/400/1.55`, `#55585B`를 사용한다. Standard Group Card와 같은 white data surface로 오인되게 만들지 않는다.

### Standard Group Card — SCREEN-02 `.section`

서로 다른 하나의 입력 묶음을 구분한다. SCREEN-02의 확정 규격은 `1px #DCDDDE` border, radius `10px`, paper surface, shadow 없음, `overflow:visible`이다. 인접 Standard Group Card 사이는 `20px`를 기본으로 한다. 강한 색상이나 별도의 회색 Header band를 쓰지 않고 border와 whitespace로 계층을 표현한다.

Header는 `min-height:0`, padding `16px 16px 0`, transparent background, divider 없음이다. Body는 padding `16px`, paper surface, 상단 divider 없음이다. Header 오른쪽에는 canonical Helper Text 또는 role이 명확한 Action을 선택적으로 배치할 수 있지만 title chrome을 바꾸지 않는다. Compact/Data Grid도 Standard Group Card 역할로 표시되는 한 이 Header/Body inset을 바꾸지 않는다.

### Group Title — SCREEN-02 `.section-head h3`

Group Card의 목적을 표시한다. typography는 `16px/600`, color는 `--ink`다. title 왼쪽 기준선은 Body content의 `16px` 기준선과 같아야 한다. Standard Group Title에는 장식 icon이나 별도 icon tile을 붙이지 않는다. 상태 전달에 반드시 필요한 icon은 title text가 아니라 별도의 status slot에 둔다.

### Standard Form Control — Input / Select / Textarea

Input/Select의 계약은 최소 높이 `46px`, padding `10px 12px`, `14px/400/1.45`, `--line-strong` border, radius `8px`, paper surface, `--ink`다. Textarea는 같은 typography와 surface를 사용하고 기본 최소 높이는 `70px`다. hover도 neutral border 계열을 유지하고 disabled는 foundation disabled color를 사용한다.

Field Label과 control 사이는 항상 `6px`다. 별도 row로 출력되는 Column Header도 첫 control row와 `6px` 간격을 사용한다. Standard Form Grid의 column gap은 SCREEN-02 기준 `12px`다. 업무상 조밀한 Data Grid는 `8~10px` column/row gap을 사용할 수 있지만 label/header와 control 사이의 `6px`는 유지한다.

### Read-only Value

Read-only value는 Standard Form Control과 `46px` 높이로 정렬하고 `14px/400`을 사용한다. 좁은 identity column에서는 horizontal padding을 줄일 수 있다.

### Helper / Guidance Text

일반 보조 설명은 Typography Roles의 Caption / Helper 계약을 사용한다. 별도 `#F7F7F7` 안내 박스는 Standard Group Card가 아니라 Guidance / Info Surface다.

### Summary / Review Card — `.prep-summary`, review surface

현재 선택 결과나 review 정보를 묶는 Standard Group Card 계열이다. padding `16px`, `#DCDDDE` border, radius `10px`, paper surface, shadow 없음이다. 콘텐츠 양에 따른 최소 높이와 Grid 열 수는 layout variant다.

### Summary Inner Surface — `.prep-summary-values`

요약값 묶음이다. `--line-strong` border, radius `8px`, `#F7F7F7`, overflow hidden을 사용한다.

### Summary Row — `.prep-summary-item`

label과 value를 `140px / minmax(0,1fr)`로 배치한다. 최소 높이 `60px`, padding `12px 16px`이며 인접 row는 `--line-strong` 상단 border로 나뉜다. `720px` 이하에서는 1열로 전환한다.

### Summary Label — `.prep-summary-label`

우측 divider를 포함하는 `13px/500` label이다. color는 `#45484B`, border는 `--line-strong`이다.

### Summary Value — `.prep-summary-value`

padding-left `24px`, `15px/600`, `--ink`이며 긴 값은 `overflow-wrap:anywhere`로 처리한다.

### Composite Form Control

하나의 bordered control 안에 input과 selector/toggle이 결합되는 형태는 SCREEN-02 combobox를 기준으로 한다. outer height `46px`, inner height `44px`, right interaction track `42px`이며 outer focus ring 하나만 표시하고 내부 input/toggle의 중복 focus ring은 제거한다. Input 옆에 별도로 붙는 Restore Utility Button도 SCREEN-02 기준 `42px × 46px`를 사용한다. 좁은 Grid라는 이유로 같은 Restore 역할을 `32px` 또는 `36px`로 축소하지 않는다.

### Detail Disclosure Action / Sub-surface — SCREEN-04 Fan Detail

반복 입력의 상세 영역을 여닫는 action은 Default Local Action 계열을 사용한다. 최소 높이 `36px`, padding `0 11px`, radius `8px`, paper surface, `--line-strong` border, `14px/500`이며 text 오른쪽에는 `16px` stroke chevron을 배치한다. `aria-expanded="true"`일 때 neutral `#F7F7F7` surface와 chevron `180deg` 회전으로 펼침 상태를 전달하고 별도의 강한 accent color는 만들지 않는다.

상세 영역은 상위 Standard Group Card 안의 중첩 data surface로 취급한다. padding `16px`, `--line-strong` border, radius `10px`, `#F7F7F7`, shadow 없음이며 title은 `15px/600/1.55`를 사용한다. 반복되는 Fan 입력 묶음은 paper surface, `--line` border, radius `8px`, padding `12px`를 사용하고 label-control `6px` 및 `46px` control 계약을 유지한다. 두 개의 Fan 묶음을 나란히 배치하는 Grid는 허용 Layout Variant이며 `760px` 이하에서는 1열로 전환한다.

### Dropdown / Combobox Menu

Composite control의 menu는 control 바로 아래 `4px`에 배치하고 좌우 폭을 outer control에 맞춘다. paper surface, `1px --line` border, shadow 없음이다. Option은 최소 높이 `30px`, padding `5px 8px`이며 hover, keyboard focus, active state는 동일한 `--brand` surface와 white text를 사용한다. native Select와 custom menu가 같은 화면에서 서로 다른 active color를 만들지 않는다.

### Action Family

| 역할 | 크기와 padding | surface / typography | 사용 범위 |
|---|---|---|---|
| Navigation Action | 최소 높이 `44px`, padding `0 18px`, radius `8px` | 기본 `14px/500`; Primary `15px/600` | 이전/다음, 완료, 핵심 진행 |
| Default Local Action | 최소 높이 `36px`, padding `7px 11px`, radius `8px` | `14px/500`, paper + `--line-strong` | 다시 시도, 일반 보조 동작 |
| Row Utility Action | `34px × 34px`, padding `0`, radius `8px` | glyph `18px/1` | 행 추가/삭제 |
| Attached Restore Action | `42px × 46px` | glyph `18px/1`, paper | 직접 입력에서 목록 복귀 |
| Shell Header Action | 최소 높이 `40px`, padding `9px 16px` | Shell component family | 새 의뢰, Agent header action |

Primary는 `--brand-strong` background/border와 white text, Secondary/Ghost는 paper background와 `--line-strong` border를 사용한다. 같은 역할의 action을 SCREEN별로 `34px`, `36px`, `44px` 사이에서 임의 변경하지 않는다. 삭제 action은 기능상 위험을 전달하되 별도 채도 높은 surface를 만들지 않고 현재 neutral remove 표현을 유지한다.

### Icon / Glyph Geometry

- 일반 control/action SVG는 `16px`, `fill:none`, `stroke:currentColor`, round linecap/linejoin, stroke-width `2`를 사용한다.
- Guidance info icon은 `20px`, stroke-width `1.8`을 사용한다.
- Navigation lock icon은 `12px`, stroke-width `2`를 사용한다.
- `+`, `−`, `↩` glyph는 `18px`, line-height `1`, 정중앙 배치를 사용한다.
- Screen Heading에는 아이콘을 붙이지 않는다. Agent identity icon은 Shell Component Family의 예외다.
- 같은 의미의 아이콘에 화면별로 원형/사각형 tile, fill icon, text glyph를 혼용하지 않는다. 의미가 같으면 하나의 geometry와 stroke 언어를 사용한다.

### Chip / Badge

Chip은 inline-flex, 최소 높이 `22px`, padding `2px 7px`, radius `8px`, `11px/500/1.2`를 사용한다. 상태별 color는 semantic feedback에만 사용하고 일반 분류나 선택 상태에 Error/Warning color를 차용하지 않는다.

### Feedback Surface

일반 guidance는 Guidance / Info Surface를 사용한다. 검증 Error/Warning은 안내 surface와 같은 padding `16px`, gap `12px`, radius `10px`, shadow 없음 규격을 사용하되 상태별로 box 전체의 border와 background를 구분한다. Error는 border `#E8B4B0`, background `#FFF2F1`, icon `#C62828`을 사용하고 Warning은 border `#E4D3AD`, background `#FFF9ED`, icon `#C77800`을 사용한다. 제목은 `15px/600/1.55`, 본문은 `13px/400/1.55`, 상태 icon block은 `20px`이며 기존 업무 의미의 icon geometry를 유지한다. 빈 feedback container는 `display:none`으로 공간을 차지하지 않는다. 동일 상태가 screen마다 chip, gray card, colored band 등 다른 도형으로 나타나지 않게 한다. Error는 다음 단계 진행을 차단하고 해당 입력 또는 오류 surface로 focus를 이동하며, Warning은 검토를 허용한다.

### Table / Matrix / Read-only Data

Column Header는 Field Label과 같은 `13px/500/1.45`를 사용한다. Cell은 `14px/400/1.45`를 기본으로 하고 compact matrix에서만 `12px` body를 사용할 수 있다. Header와 첫 control/data row 사이는 `6px`, cell padding은 같은 table 안에서 동일해야 한다. Read-only field가 editable control과 같은 row에 있으면 높이 `46px`, radius `8px`, typography `14px/400`으로 정렬한다.

### Empty / Disabled / Modal

Empty surface는 `1px dashed --line`, radius `8px`, `--soft` background, padding `12px`, muted `13px/1.45`를 사용한다. Disabled control은 `--disabled-bg`, `--disabled-text`, not-allowed cursor를 사용한다. Modal dialog는 paper surface, `1px --line` border, radius `10px`, `--shadow`, padding `22px`를 사용하며 내부 action은 Action Family를 재사용한다.

## 6. Component 사용 원칙

### 6.1 Component Identity 불변 항목

같은 역할의 component에서는 다음을 바꿀 수 없다.

- font size, weight, line-height, text color
- border color/width, radius, background, shadow
- component 내부 padding과 label/header-to-control gap
- control과 action의 role별 높이/폭
- icon size, stroke, fill, glyph, 정렬 방식
- hover, focus, selected, readonly, disabled, error, warning state language

Selector 이름이나 HTML 구조가 다르더라도 사용자에게 같은 도구로 인식되면 같은 Component Identity를 적용한다. 화면 scoped CSS는 업무 배치만 조정해야 하며 동일 component의 chrome을 새로 만들지 않는다.

### 6.2 허용 Layout Variant

화면 목적에 따라 다음은 달라질 수 있다.

- Grid column 수와 비율
- 좁은 identity column의 폭
- responsive stacking과 breakpoint
- row 순서, span, wrap, overflow
- Standard Grid `12px` 또는 Compact/Data Grid `8~10px`의 외부 row/column gap
- 업무 정책에 의해 정해지는 고정 column 폭

Layout Variant는 Card Header/Body `16px` inset, label/header-to-control `6px`, component typography, control 높이, focus, icon, action role 크기를 바꾸는 근거가 아니다.

### 6.3 공통 적용 원칙

- 하나의 Screen에는 하나의 `24px/600` Screen Heading을 둔다.
- 서로 다른 목적의 입력 묶음은 SCREEN-02 Standard Group Card hierarchy로 구분한다.
- hierarchy는 강한 색상보다 border와 whitespace를 우선 사용한다.
- Primary Action은 charcoal 계열을 사용하고 한 Screen에서 가장 중요한 진행 action에 배정한다.
- Caption과 Helper는 canonical helper typography를 재사용한다.
- Workspace 내부 card에는 shadow를 중첩하지 않는다.
- Error/Warning semantic color는 neutral UI color와 별도로 취급한다.
- 동일 역할을 위한 새 selector가 필요하더라도 기존 Component Contract 값을 그대로 연결한다.

## 7. Workspace Token 관계

`.workspace-shell`은 두 번째 독립 token 체계를 만들지 않고 root foundation을 Workspace 의미에 맞게 alias한다.

| Workspace token | 연결 대상 | 의미 |
|---|---|---|
| `--request-workspace-font` | 동일 공통 font stack | Workspace text/control font |
| `--request-workspace-page` | `var(--bg)` | page 역할 |
| `--request-workspace-content` | `var(--bg)` | content 배경 역할 |
| `--request-workspace-surface` | `var(--paper)` | card/control surface |
| `--request-workspace-border` | `var(--line)` | Workspace border |
| `--request-workspace-ink` | `var(--ink)` | Workspace primary text |
| `--request-workspace-muted` | `var(--muted)` | Workspace secondary text |
| `--request-workspace-accent` | `var(--accent)` | Workspace primary/active state |
| `--request-workspace-radius` | `10px` | 일반 Workspace section radius |
| `--request-workspace-shadow` | `var(--shadow)` | Workspace shell shadow; Standard Group Card에는 미사용 |
| `--request-workspace-card-content-padding` | `10px` | 현재 legacy compact body 값; canonical Standard Group Card `16px`의 근거로 사용하지 않음 |
| `--request-workspace-card-section-gap` | `20px` | section 간 gap |

관계는 `Root token → --request-workspace-* alias → Workspace component`다. 예를 들어 `--paper → --request-workspace-surface → Workspace card/control`로 전달된다. Agent Dock은 `.workspace-shell`의 sibling이므로 Workspace alias가 아니라 root foundation을 직접 사용한다. 현재 코드에는 `--ui-*`나 `--design-*` 계열의 두 번째 design token layer가 없다. 기존 alias의 이름만 같다는 이유로 legacy `10px` padding이나 section shadow를 canonical component에 적용하지 않는다.

## 8. 전체 화면 현행 Audit

아래 표는 현재 `ui.py`의 최종 cascade를 SCREEN-02 표준과 비교한 결과다. `불일치`는 현재 기능 오류가 아니라 이후 visual migration에서 고쳐야 할 항목을 뜻한다.

| 범위 | 일치 항목 | 불일치 / migration 대상 | 허용 Layout Variant |
|---|---|---|---|
| SCREEN-01 | `24px` heading, `16px` card title, white/radius `10px` card, `46px` control, label-control `6px`; 공용 Restore primitive `42×46px` (현재 화면에는 직접 입력 복귀 동작 없음) | 없음 | 분류 Grid 비율, Summary layout |
| SCREEN-02 | Canonical heading/description/card/field/control/composite/action | 없음 | 4-column/2-column form 구성 |
| SCREEN-03 | heading/description, card chrome, title, Column Header–control `6px`, `46px` control, read-only height, `34px` row action, 표준 Error Surface와 진행 차단 gate | 없음 | 제품 column 비율과 `9px` Data Grid gap |
| SCREEN-04 | heading/description, `16px` Card Header/Body inset, title typography, label-control `6px`, `46px` control, composite `42px` track, `42×46px` Restore Action, `34px` row action, Fan Detail Local Action/Sub-surface | 없음 | identity/Fan/HEX column 비율, Fan Count 전체 폭 `90px`, Fan Detail 2열→1열 반응형 Grid, `8~12px` Grid gap |
| SCREEN-05 | `24px` heading, `16px` Card Header/Body inset, transparent Header, `16px` title, no section shadow, `36px` Case Local Action, `44px` Navigation Action, Matrix Header `13px/500/1.45`, 상태색 box의 표준 Error/Warning Surface, 오류 진행 차단 gate | 없음 | Case Matrix 열 수, sticky header, cell padding, matrix overflow |
| SCREEN-06 | `24px` heading, `16px` Card Header/Body inset, transparent Header, `16px` title, no section shadow/title icon, `44px` Word Primary Action, Preview Header `13px/500/1.45`, read-only value `14px/400/1.45`, `14px` inline 누락 icon, SCREEN-03/05와 공용인 상태색 Error/Warning Surface | 없음 | Preview/Word 정보 구조와 review Grid |
| Global Shell / Agent | Foundation, Shell surface, navigation, resizer, Agent message/input 규격 | Workspace card 표준을 Shell card에 역적용하지 않음 | desktop/overlay, Workspace-Agent 비율 |
| Modal / Feedback | Modal radius `10px`, SCREEN-03/05/06 Error/Warning 상태색 surface, `20px` icon, 빈 container 비표시 | 없음 | message 길이와 action 수 |

이 Audit에서 확인된 차이는 문서에 의해 허용된 별도 디자인 언어가 아니다. 기능/Grid를 보존하는 화면별 migration task에서 Component Identity만 SCREEN-02 표준으로 정합화한다.

## 9. Migration / 신규 화면 체크

새 화면 또는 기존 화면을 다룰 때 다음 순서로 SCREEN-02와 정합성을 확인한다.

1. Screen Heading과 Description이 canonical typography/spacing을 사용하는가.
2. 같은 목적의 Group Card가 `16px` Header/Body inset, transparent Header, no divider/no shadow를 사용하는가.
3. Field Label 또는 Column Header와 control/data row 사이가 `6px`인가.
4. form control, read-only value, composite control이 canonical height, typography, radius, focus를 사용하는가.
5. action이 기능 역할에 맞는 Action Family 크기를 사용하며 같은 icon/glyph를 재사용하는가.
6. Guidance, Feedback, Empty, Disabled 상태가 각각 정해진 surface family를 사용하는가.
7. Compact/Data Layout이 component chrome이나 내부 spacing까지 변경하지 않았는가.
8. Main Workspace와 Agent Dock의 독립 surface 및 desktop/overlay 관계를 유지하는가.
9. 새 token, semantic class, shadow, icon language를 화면 한 곳만 위해 만들지 않았는가.

표준 변경과 화면 migration은 분리한다. 이 문서의 표준을 바꾸려면 SCREEN-02 canonical 변경을 먼저 승인하고, 개별 화면의 정합화는 기능/Grid를 보존하는 별도 task로 수행한다.
