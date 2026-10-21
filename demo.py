# ==========================================================================
# FIX 1 of 6: replace your two API_BASE_URL / API_KEY lines (near line 30)
# ==========================================================================
def _secret(name, default=""):
    try:
        return st.secrets[name]
    except Exception:
        return os.environ.get(name, default)

API_BASE_URL = _secret("API_BASE_URL", "https://identity-trust-api.onrender.com").rstrip("/")
API_KEY = _secret("API_KEY", "")   # set it in Streamlit "Secrets", never in the code
API_FIELDS = ['emirates_id', 'given_name', 'family_name', 'date_of_birth', 'gender',
              'nationality', 'source_facility', 'registration_date', 'canonical_id']


# ==========================================================================
# FIX 2 of 6: add these helpers right after get_recent_decisions()
# ==========================================================================
def _api_headers():
    return {"X-API-Key": API_KEY} if API_KEY else {}


def api_health():
    """Wake the Render server and report whether it needs an API key."""
    try:
        r = requests.get(f"{API_BASE_URL}/health", timeout=60)
        r.raise_for_status()
        return True, r.json()
    except Exception as e:
        return False, str(e)


def api_post(path, payload, timeout=120):
    """POST and report honestly (the old code ignored HTTP errors). Returns (ok, message)."""
    try:
        r = requests.post(f"{API_BASE_URL}{path}", json=payload,
                          headers=_api_headers(), timeout=timeout)
    except Exception as e:
        return False, f"Could not reach the API: {e}"
    if r.status_code in (401, 403):
        return False, f"The API rejected the request ({r.status_code}): the API key is missing or wrong."
    if r.status_code >= 400:
        return False, f"API error {r.status_code}: {r.text[:300]}"
    return True, "ok"


def to_api_records(raw_df):
    """Map arbitrary CSV columns to the fields the API expects, as clean strings."""
    df = raw_df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    mapping, _, _ = map_columns(df)
    df = df.rename(columns=mapping)
    cols = [c for c in API_FIELDS if c in df.columns]
    df = df[cols].astype(str).replace({'nan': '', 'NaN': '', 'None': '', '<NA>': ''}).fillna('')
    return df.to_dict(orient='records')


def store_batch(csv_bytes, key):
    """Send a batch to /assess-batch once per file (not on every Streamlit rerun)."""
    if st.session_state.get('stored_key') == key:
        return st.session_state.get('store_result')
    raw = pd.read_csv(io.BytesIO(csv_bytes), dtype=str).fillna('')   # dtype=str keeps IDs intact
    records = to_api_records(raw)
    ok, msg, sent = True, 'ok', 0
    for i in range(0, len(records), 500):
        chunk = records[i:i + 500]
        ok, msg = api_post('/assess-batch', chunk)
        if not ok:
            break
        sent += len(chunk)
    result = (ok, msg, sent, len(records))
    st.session_state['stored_key'] = key
    st.session_state['store_result'] = result
    return result


# ==========================================================================
# FIX 3 of 6: in pg_batch(), replace everything from the comment
#   "# --- NEW: SEND TO API FOR DATABASE STORAGE ---"
# down to (and including) the "except Exception as e: st.warning(...)" line
# with this (keep the 4-space indentation inside pg_batch):
# ==========================================================================
#     with st.spinner('Sending records to the Trust Gate API (the free server can take up to a minute to wake)...'):
#         ok, msg, sent, total = store_batch(uploaded_file.getvalue(), f"{uploaded_file.name}:{uploaded_file.size}")
#     if ok:
#         st.success(f'Stored {sent:,} of {total:,} records in the cloud database.')
#     else:
#         st.error(f'Not stored in the cloud database. {msg}')


# ==========================================================================
# FIX 4 of 6: in load_demo_batch(), add these lines at the end
# (the demo button never sent anything to the database before)
# ==========================================================================
#     ok, msg, sent, total = store_batch(data, f"demo:{region}:{datetime.now():%H%M%S}")
#     st.toast(f'Demo batch stored in the cloud database ({sent} records).' if ok else f'Not stored: {msg}')


# ==========================================================================
# FIX 5 of 6: in pg_audit(), replace everything from
#   "# --- NEW: Fetch live data from Neon via API ---"
# down to the line "if chain_msg: st.caption(...)" EXCLUDING the k1/k2/k3 KPI lines.
# i.e. replace from db_df = get_recent_decisions(...) through the
# "elif log_exists: ... except Exception as ex: ..." block with:
# ==========================================================================
#     db_df = get_recent_decisions(limit=500)
#     log_exists = os.path.exists(AUDIT_LOG_PATH)
#     if not db_df.empty:
#         results_df = db_df.copy()
#         for col, default in [('given_name', ''), ('family_name', ''), ('source_facility', ''),
#                              ('explanation', 'Stored decision from the cloud audit log.'),
#                              ('primary_issue', 'None')]:
#             if col not in results_df.columns:
#                 results_df[col] = default
#     n_entries = len(db_df) if not db_df.empty else 0
#     chain_ok, chain_msg = None, 'No log file found yet.'
#     if log_exists:
#         if db_df.empty:
#             with open(AUDIT_LOG_PATH, 'rb') as f:
#                 n_entries = sum(1 for _ in f)
#         try:
#             chain_ok, chain_msg = verify_chain(AUDIT_LOG_PATH)
#         except Exception as ex:
#             chain_ok, chain_msg = False, str(ex)
#         if not db_df.empty:
#             chain_msg = f'{chain_msg} (checked on this session log; the cloud database holds {len(db_df):,} stored decisions)'


# ==========================================================================
# FIX 6 of 6: add to pg_config() so you can see the connection at a glance
# ==========================================================================
#     st.markdown('### Cloud connection')
#     if st.button('Check cloud connection'):
#         with st.spinner('Waking the server...'):
#             ok, info = api_health()
#         if not ok:
#             st.error(f'API unreachable: {info}')
#         else:
#             st.success('API is awake.')
#             st.write(f"API key required: **{info.get('auth_required')}** | key set in this app: **{bool(API_KEY)}**")
#             if info.get('auth_required') and not API_KEY:
#                 st.error('The API needs a key but this app has none. Add API_KEY to Streamlit Secrets.')
