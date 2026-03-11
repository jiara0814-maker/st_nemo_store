import streamlit as st
import pandas as pd
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
import json
import os

# 페이지 설정
st.set_page_config(page_title="네모(NEMO) 인텔리전스 대시보드", layout="wide")

# 컬럼명 한글 맵핑 (개선사항 4)
COL_MAP = {
    'title': '매물명',
    'businessLargeCodeName': '업종대분류',
    'businessMiddleCodeName': '추천업종',
    'deposit': '보증금(만원)',
    'monthlyRent': '월세(만원)',
    'premium': '권리금(만원)',
    'maintenanceFee': '관리비(만원)',
    'size': '면적(㎡)',
    'floor': '층수',
    'nearSubwayStation': '인근지하철역',
    'viewCount': '조회수',
    'favoriteCount': '찜수'
}

# 세션 상태 초기화
if 'selected_item_id' not in st.session_state:
    st.session_state.selected_item_id = None

# 데이터 로드 및 전처리
@st.cache_data
def load_data():
    # 파일 경로 설정 (로컬 및 배포 환경 호환)
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    db_path = os.path.join(base_dir, "data", "nemostore_items.db")
    
    if not os.path.exists(db_path):
        # 만약 위 경로에 없다면 현재 작업 디렉토리 기준 다시 시도
        db_path = "nemostore/data/nemostore_items.db"
        if not os.path.exists(db_path):
            st.error(f"데이터베이스 파일을 찾을 수 없습니다: {db_path}")
            return pd.DataFrame()
    
    conn = sqlite3.connect(db_path)
    df = pd.read_sql_query("SELECT * FROM items", conn)
    conn.close()
    
    # 수치형 변환
    numeric_cols = ['deposit', 'monthlyRent', 'premium', 'maintenanceFee', 'size', 'viewCount', 'favoriteCount', 'areaPrice', 'floor']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            
    # 사진 URL 처리
    def parse_urls(url_str):
        try:
            if isinstance(url_str, str) and url_str.startswith('['):
                return json.loads(url_str.replace("'", '"'))
            return []
        except:
            return []
            
    df['photo_list'] = df['smallPhotoUrls'].apply(parse_urls)
    df['main_image'] = df['photo_list'].apply(lambda x: x[0] if x else "")
    
    # 지도 시각화를 위한 좌표 맵핑 (상세 주소가 없으므로 인근 지하철역 기반 임시 좌표 설정)
    station_coords = {
        '망원역': (37.5560, 126.9101),
        '마포구청역': (37.5635, 126.9033),
        '합정역': (37.5494, 126.9138),
        '상수역': (37.5477, 126.9229),
        '광흥창역': (37.5474, 126.9319)
    }
    
    def get_coords(station_str):
        for name, coords in station_coords.items():
            if name in str(station_str):
                return coords
        return (37.5560, 126.9101) # 기본값 (망원역 인근)

    df['coords'] = df['nearSubwayStation'].apply(get_coords)
    df['lat'] = df['coords'].apply(lambda x: x[0])
    df['lon'] = df['coords'].apply(lambda x: x[1])
    
    return df

# 필터링 기능
def apply_filters(df):
    st.sidebar.header("🔍 검색 및 필터")
    
    # 검색어 필터 (갤러리 검색 속도 개선 - 캐싱 및 간결한 로직)
    search = st.sidebar.text_input("매물 제목 검색", "").strip()
    
    biz_types = ["전체"] + sorted(df['businessLargeCodeName'].unique().tolist())
    selected_biz = st.sidebar.selectbox("업종 대분류", biz_types)
    
    st.sidebar.subheader("💰 가격 조건 (만원)")
    dep_range = st.sidebar.slider("보증금", int(df['deposit'].min()), int(df['deposit'].max()), (0, int(df['deposit'].max())))
    rent_range = st.sidebar.slider("월세", int(df['monthlyRent'].min()), int(df['monthlyRent'].max()), (0, int(df['monthlyRent'].max())))
    prem_range = st.sidebar.slider("권리금", int(df['premium'].min()), int(df['premium'].max()), (0, int(df['premium'].max())))
    
    temp_df = df.copy()
    if search:
        temp_df = temp_df[temp_df['title'].str.contains(search, case=False, na=False)]
    if selected_biz != "전체":
        temp_df = temp_df[temp_df['businessLargeCodeName'] == selected_biz]
        
    temp_df = temp_df[
        (temp_df['deposit'].between(dep_range[0], dep_range[1])) &
        (temp_df['monthlyRent'].between(rent_range[0], rent_range[1])) &
        (temp_df['premium'].between(prem_range[0], prem_range[1]))
    ]
    return temp_df

# 1) 지도 시각화 (Map View)
def show_map(df):
    st.subheader("📍 매물 위치 분포 (지도)")
    # 지역별 밀집도 표시 (Mapbox scatter)
    fig = px.scatter_mapbox(df, lat="lat", lon="lon", hover_name="title", 
                            hover_data=["deposit", "monthlyRent", "businessMiddleCodeName"],
                            color="businessLargeCodeName", size="monthlyRent",
                            zoom=13, height=500)
    fig.update_layout(mapbox_style="open-street-map")
    fig.update_layout(margin={"r":0,"t":0,"l":0,"b":0})
    st.plotly_chart(fig, use_container_width=True)

# 2) 상대적 가치 평가 지표 (Benchmarking)
def show_benchmark(item, df):
    st.markdown("### 📈 상대적 가치 평가 (Benchmarking)")
    
    # 동일 업종 평균 계산
    avg_biz_rent = df[df['businessLargeCodeName'] == item['businessLargeCodeName']]['monthlyRent'].mean()
    avg_area_rent = df[df['nearSubwayStation'].str.contains(item['nearSubwayStation'].split(',')[0])]['monthlyRent'].mean()
    
    def get_diff_pct(val, avg):
        if avg == 0: return 0
        return ((val - avg) / avg) * 100

    rent_biz_diff = get_diff_pct(item['monthlyRent'], avg_biz_rent)
    rent_area_diff = get_diff_pct(item['monthlyRent'], avg_area_rent)
    
    bm_col1, bm_col2 = st.columns(2)
    with bm_col1:
        color = "red" if rent_biz_diff > 0 else "green"
        st.metric(label="동일 업종 평균 대비 월세", value=f"{item['monthlyRent']:,} 만원", 
                  delta=f"{rent_biz_diff:+.1f}%", delta_color="inverse")
        st.caption(f"동일 업종({item['businessLargeCodeName']}) 평균: {int(avg_biz_rent):,}만원")

    with bm_col2:
        st.metric(label="동일 지역(역세권) 평균 대비 월세", value=f"{item['monthlyRent']:,} 만원", 
                  delta=f"{rent_area_diff:+.1f}%", delta_color="inverse")
        st.caption(f"동일 지역 평균: {int(avg_area_rent):,}만원")

# 3) 층별 임대료 비교 분석
def show_floor_analysis(df):
    st.subheader("🏢 층별 평균 임대료 분석")
    floor_data = df.groupby('floor')['monthlyRent'].mean().reset_index()
    # 층수 정렬 (-1 지하 등)
    floor_data = floor_data.sort_values('floor')
    fig = px.bar(floor_data, x='floor', y='monthlyRent', 
                 title="층별 평균 월세 (만원)", 
                 labels={'floor': '층수', 'monthlyRent': '평균 월세(만원)'},
                 color='monthlyRent', color_continuous_scale='Viridis')
    st.plotly_chart(fig, use_container_width=True)

# 메인 갤러리 뷰
def show_gallery(df):
    st.subheader(f"🏠 매물 갤러리 ({len(df)}건)")
    
    cols = st.columns(4) # 4열로 확장
    for idx, row in df.reset_index().iterrows():
        with cols[idx % 4]:
            with st.container(border=True):
                img_url = row['main_image'] if row['main_image'] else "https://via.placeholder.com/300x200?text=No+Image"
                st.image(img_url, use_container_width=True)
                st.markdown(f"**{row['title'][:20]}**")
                st.caption(f"{row['businessMiddleCodeName']} | {row['nearSubwayStation']}")
                st.markdown(f"💰 **{row['deposit']:,}/{row['monthlyRent']:,}** (권 {row['premium']:,})")
                if st.button("상세보기", key=f"btn_{row['id']}"):
                    st.session_state.selected_item_id = row['id']
                    st.rerun()

# 상세 페이지
def show_detail(df, item_id):
    item = df[df['id'] == item_id].iloc[0]
    
    if st.button("⬅️ 목록으로 돌아가기"):
        st.session_state.selected_item_id = None
        st.rerun()
        
    st.markdown(f"## {item['title']}")
    st.markdown("---")
    
    # 벤치마킹 지표 표시
    show_benchmark(item, df)
    st.markdown("---")
    
    col1, col2 = st.columns([1, 1])
    with col1:
        st.subheader("🖼️ 매물 사진")
        photos = item['photo_list']
        if photos:
            for p in photos:
                st.image(p, use_container_width=True)
            
    with col2:
        st.subheader("📋 상세 내역 (사용자 친화 언어)")
        with st.container(border=True):
            # 한글 컬럼명 적용
            st.markdown(f"- **{COL_MAP['deposit']}**: `{item['deposit']:,}`")
            st.markdown(f"- **{COL_MAP['monthlyRent']}**: `{item['monthlyRent']:,}`")
            st.markdown(f"- **{COL_MAP['premium']}**: `{item['premium']:,}`")
            st.markdown(f"- **{COL_MAP['maintenanceFee']}**: `{item['maintenanceFee']:,}`")
            st.markdown(f"- **{COL_MAP['size']}**: `{item['size']}`")
            st.markdown(f"- **{COL_MAP['floor']}**: `{item['floor']}`")
            st.markdown(f"- **{COL_MAP['businessLargeCodeName']}**: {item['businessLargeCodeName']}")
            st.markdown(f"- **{COL_MAP['businessMiddleCodeName']}**: {item['businessMiddleCodeName']}")
            st.markdown(f"- **{COL_MAP['nearSubwayStation']}**: {item['nearSubwayStation']}")
            st.markdown(f"- **{COL_MAP['viewCount']}**: {item['viewCount']}회")

def main():
    df = load_data()
    if df.empty: return
    
    filtered_df = apply_filters(df)
    
    if st.session_state.selected_item_id:
        show_detail(df, st.session_state.selected_item_id)
    else:
        # 상단 통합 분석 섹션
        tab1, tab2 = st.tabs(["🗺️ 지도 및 갤러리", "📊 심층 통계 분석"])
        
        with tab1:
            show_map(filtered_df)
            show_gallery(filtered_df)
            
        with tab2:
            show_floor_analysis(filtered_df)
            
            # Plotly 차트 리뉴얼
            c1, c2 = st.columns(2)
            with c1:
                fig_pie = px.pie(filtered_df, names='businessLargeCodeName', title='업종 대분류 비중 (Plotly)')
                st.plotly_chart(fig_pie, use_container_width=True)
            with c2:
                fig_scatter = px.scatter(filtered_df, x='size', y='monthlyRent', color='businessLargeCodeName',
                                         size='deposit', hover_name='title', title='면적 vs 월세')
                st.plotly_chart(fig_scatter, use_container_width=True)

if __name__ == "__main__":
    main()
