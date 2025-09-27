import streamlit as st



if __name__ == '__main__':
    demo1 = 'データ可視化'
    demo2 = '皮膚タッチ認識'

    page = st.sidebar.selectbox('デモ切り替え', [demo1, demo2])
    # Custom HTML/CSS for the banner
    st.markdown( """
    <div class="banner">
        <img src="./app/static/wear_senstick_resize.jpg" alt="Banner Image">
    </div>
    <style>
        .banner {
            width: 100%;
            height: 100%;
            overflow: hidden;
        }
        .banner img {
            width: 100%;
            height: 100%;
            object-fit: cover;
        }
    </style>
    """, unsafe_allow_html=True)


    if page == demo1:
        st.title('データ可視化')
        st.write('準備中')
    elif page == demo2:
        st.title('皮膚タッチ認識')
        st.write('準備中')