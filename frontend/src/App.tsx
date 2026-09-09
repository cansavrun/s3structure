import { useEffect, useState } from 'react';
import { useInfiniteQuery, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ArrowDownToLine,
  ArrowUpRight,
  ChevronRight,
  File,
  Folder,
  FolderOpen,
  HardDrive,
  LayoutGrid,
  List,
  LoaderCircle,
  LockKeyhole,
  LogOut,
  RefreshCw,
  Search,
  ShieldCheck,
  Table2,
  X,
} from 'lucide-react';
import {
  api,
  ApiError,
  downloadUrl,
  errorMessage,
  formatBytes,
  type FileEntry,
  type FilePage,
  type Me,
} from './api';
import { Brand } from './components/Brand';
import { Login } from './components/Login';
import { CsvPreview } from './components/CsvPreview';

export function App() {
  const queryClient = useQueryClient();
  const me = useQuery({
    queryKey: ['me'],
    queryFn: async ({ signal }) => {
      try {
        return await api<Me>('/me', { signal });
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) return null;
        throw err;
      }
    },
  });

  useEffect(() => {
    const expire = () => {
      void queryClient.cancelQueries();
      queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== 'me' });
      queryClient.setQueryData(['me'], null);
    };
    window.addEventListener('tenantfiles:unauthorized', expire);
    return () => window.removeEventListener('tenantfiles:unauthorized', expire);
  }, [queryClient]);

  function loggedIn(data: Me) {
    // Önceki müşterinin liste ve CSV cache'i oturum değişiminde silinir.
    void queryClient.cancelQueries();
    queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== 'me' });
    queryClient.setQueryData(['me'], data);
  }
  async function logout() {
    await api('/auth/logout', { method: 'POST' });
    void queryClient.cancelQueries();
    queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== 'me' });
    queryClient.setQueryData(['me'], null);
  }
  if (me.isPending)
    return (
      <main className="loading-page">
        <Brand />
        <span className="spinner" />
        <p>Çalışma alanı hazırlanıyor…</p>
      </main>
    );
  if (me.error)
    return (
      <main className="loading-page">
        <Brand />
        <p role="alert">{errorMessage(me.error)}</p>
        <button className="primary" onClick={() => void me.refetch()}>
          Yeniden dene
        </button>
      </main>
    );
  return me.data ? (
    <Workspace key={me.data.customer.id} me={me.data} onLogout={logout} />
  ) : (
    <Login onLogin={loggedIn} />
  );
}

function Workspace({ me, onLogout }: { me: Me; onLogout: () => Promise<void> }) {
  const [path, setPath] = useState('');
  const [search, setSearch] = useState('');
  const [layout, setLayout] = useState<'list' | 'grid'>('list');
  const [preview, setPreview] = useState<FileEntry | null>(null);
  const [logoutError, setLogoutError] = useState('');
  const [loggingOut, setLoggingOut] = useState(false);
  const listing = useInfiniteQuery({
    queryKey: ['files', me.customer.id, path],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) => {
      const params = new URLSearchParams({ path });
      if (pageParam) params.set('cursor', pageParam);
      return api<FilePage>(`/files?${params}`, { signal });
    },
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });
  const folders = listing.data?.pages.flatMap((page) => page.folders) ?? [];
  const files = listing.data?.pages.flatMap((page) => page.files) ?? [];
  // Arama türetilmiş veridir; gereksiz useEffect ve ikinci bir state oluşturmayız.
  const filter = search.toLocaleLowerCase('tr');
  const visibleFolders = folders.filter((item) =>
    item.name.toLocaleLowerCase('tr').includes(filter),
  );
  const visibleFiles = files.filter((item) => item.name.toLocaleLowerCase('tr').includes(filter));
  const parts = path.split('/').filter(Boolean);
  const totalSize = files.reduce((sum, item) => sum + item.size, 0);

  function navigate(next: string) {
    setPath(next);
    setSearch('');
    setPreview(null);
  }
  async function exit() {
    setLoggingOut(true);
    setLogoutError('');
    try {
      await onLogout();
    } catch (err) {
      setLogoutError(errorMessage(err));
      setLoggingOut(false);
    }
  }

  return (
    <div className="workspace">
      <a className="skip-link" href="#main-content">
        İçeriğe geç
      </a>
      <aside className="sidebar">
        <Brand />
        <div className="workspace-picker">
          <span className="avatar">{me.customer.name.slice(0, 1)}</span>
          <div>
            <strong>{me.customer.name}</strong>
            <span>Müşteri çalışma alanı</span>
          </div>
          <LockKeyhole size={14} />
        </div>
        <p className="nav-label">ÇALIŞMA ALANI</p>
        <nav aria-label="Ana menü">
          <button className="nav-item active" onClick={() => navigate('')}>
            <FolderOpen size={19} /> Dosyalarım <ChevronRight size={16} />
          </button>
        </nav>
        <div className="sidebar-note">
          <div className="shield-mark">
            <ShieldCheck size={22} />
          </div>
          <h3>Size özel. Güvenle.</h3>
          <p>Yalnızca hesabınıza tanımlı dosyalar burada görünür.</p>
          <span>
            <span className="status-dot" /> Erişim koruması etkin
          </span>
        </div>
        <div className="sidebar-bottom">
          <div className="user-info">
            <span className="user-avatar">{me.customer.name.slice(0, 2).toUpperCase()}</span>
            <div>
              <strong>{me.key_name}</strong>
              <span>Salt okunur erişim</span>
            </div>
          </div>
          <button className="logout-button" onClick={() => void exit()} disabled={loggingOut}>
            <LogOut size={16} />
            {loggingOut ? 'Çıkış yapılıyor…' : 'Güvenli çıkış'}
          </button>
          {logoutError && (
            <p role="alert" className="logout-error">
              {logoutError}
            </p>
          )}
        </div>
      </aside>
      <div className="workspace-body">
        <header className="topbar">
          <span>
            Çalışma alanı <ChevronRight size={13} /> <strong>Dosyalarım</strong>
          </span>
          <span className="private-badge">
            <LockKeyhole size={13} /> Özel alan
          </span>
        </header>
        <main id="main-content" className="main-content">
          <div className="page-heading">
            <div>
              <span className="eyebrow">DOSYA MERKEZİ</span>
              <h1>Her şey yerli yerinde.</h1>
              <p>Raporlarınızı keşfedin, CSV verilerini inceleyin ve dosyalarınızı indirin.</p>
            </div>
            <span className="heading-icon">
              <FolderOpen size={30} strokeWidth={1.4} />
            </span>
          </div>
          <div className="summary-cards">
            <div className="summary-card">
              <span className="summary-icon">
                <Folder size={20} />
              </span>
              <div>
                <span>Bu klasörde</span>
                <strong>
                  {folders.length}
                  <small> klasör</small>
                </strong>
              </div>
            </div>
            <div className="summary-card">
              <span className="summary-icon blue">
                <File size={20} />
              </span>
              <div>
                <span>Yüklenen dosyalar</span>
                <strong>
                  {files.length}
                  <small> dosya</small>
                </strong>
              </div>
            </div>
            <div className="summary-card">
              <span className="summary-icon amber">
                <HardDrive size={20} />
              </span>
              <div>
                <span>Yüklenen dosyaların boyutu</span>
                <strong>{formatBytes(totalSize)}</strong>
              </div>
            </div>
          </div>
          <section className="file-browser" aria-label="Dosya gezgini">
            <div className="browser-heading">
              <nav className="breadcrumbs" aria-label="Klasör yolu">
                <button onClick={() => navigate('')} aria-label="Tüm dosyalar">
                  <FolderOpen size={17} />
                  <span>Tüm dosyalar</span>
                </button>
                {parts.map((part, i) => (
                  <span key={i}>
                    <ChevronRight size={14} />
                    <button
                      aria-current={i === parts.length - 1 ? 'page' : undefined}
                      onClick={() => navigate(parts.slice(0, i + 1).join('/') + '/')}
                    >
                      {part}
                    </button>
                  </span>
                ))}
              </nav>
              <button
                className="icon-button"
                title="Yenile"
                aria-label="Dosyaları yenile"
                disabled={listing.isFetching}
                onClick={() => void listing.refetch()}
              >
                <RefreshCw size={17} className={listing.isFetching ? 'spin' : ''} />
              </button>
            </div>
            <div className="browser-controls">
              <label className="search-field">
                <Search size={17} />
                <input
                  placeholder="Bu klasörde ara…"
                  aria-label="Bu klasörde ara"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
                {search && (
                  <button aria-label="Aramayı temizle" onClick={() => setSearch('')}>
                    <X size={14} />
                  </button>
                )}
              </label>
              <div className="controls-right">
                <span className="entry-count">
                  {visibleFolders.length + visibleFiles.length} öğe
                </span>
                <div className="view-toggle">
                  <button
                    aria-label="Liste görünümü"
                    aria-pressed={layout === 'list'}
                    onClick={() => setLayout('list')}
                  >
                    <List size={17} />
                  </button>
                  <button
                    aria-label="Kart görünümü"
                    aria-pressed={layout === 'grid'}
                    onClick={() => setLayout('grid')}
                  >
                    <LayoutGrid size={16} />
                  </button>
                </div>
              </div>
            </div>
            {listing.isPending ? (
              <div role="status" className="loading-state">
                <LoaderCircle size={22} className="spin" /> Dosyalar yükleniyor…
              </div>
            ) : listing.error ? (
              <div role="alert" className="error-box browser-error">
                {errorMessage(listing.error)}
                <button className="text-button" onClick={() => void listing.refetch()}>
                  Yeniden dene
                </button>
              </div>
            ) : !visibleFolders.length && !visibleFiles.length ? (
              <div className="empty-state">
                <FolderOpen size={35} strokeWidth={1.3} />
                <h3>{search ? 'Eşleşen dosya bulunamadı' : 'Bu klasör henüz boş'}</h3>
                <p>
                  {search
                    ? 'Başka bir adla arayın veya sonraki öğeleri yükleyin.'
                    : 'Yeni dosyalar yöneticiniz tarafından eklendiğinde burada görünecek.'}
                </p>
              </div>
            ) : (
              <div className={`entries ${layout}`} role="list" aria-label="Klasörler ve dosyalar">
                {layout === 'list' && (
                  <div className="table-labels" aria-hidden="true">
                    <span>DOSYA ADI</span>
                    <span>BOYUT</span>
                    <span>SON GÜNCELLEME</span>
                    <span>İŞLEMLER</span>
                  </div>
                )}
                {visibleFolders.map((folder) => (
                  <div className="entry folder-entry" role="listitem" key={folder.path}>
                    <button className="entry-name" onClick={() => navigate(folder.path)}>
                      <span className="folder-icon">
                        <Folder size={23} strokeWidth={1.6} />
                      </span>
                      <span>
                        <strong>{folder.name}</strong>
                        <small>Klasör</small>
                      </span>
                    </button>
                    <span className="entry-size">—</span>
                    <span className="entry-date">—</span>
                    <button
                      className="icon-button folder-open"
                      aria-label={`${folder.name} klasörünü aç`}
                      onClick={() => navigate(folder.path)}
                    >
                      <ArrowUpRight size={17} />
                    </button>
                  </div>
                ))}
                {visibleFiles.map((file) => (
                  <div className="entry" role="listitem" key={file.path}>
                    <div className="entry-name">
                      <span className={`file-icon ${file.is_csv ? '' : 'neutral'}`}>
                        {file.is_csv ? <Table2 size={22} /> : <File size={22} />}
                      </span>
                      <span>
                        <strong>{file.name}</strong>
                        <small>{file.is_csv ? 'CSV dosyası' : 'Dosya'}</small>
                      </span>
                    </div>
                    <span className="entry-size">{formatBytes(file.size)}</span>
                    <span className="entry-date">
                      {new Date(file.modified_at).toLocaleDateString('tr-TR', {
                        day: '2-digit',
                        month: 'short',
                        year: 'numeric',
                      })}
                    </span>
                    <div className="entry-actions">
                      {file.is_csv && (
                        <button
                          className="preview-button"
                          aria-label={`${file.name} önizle`}
                          onClick={() => setPreview(file)}
                        >
                          Önizle
                        </button>
                      )}
                      <a
                        className="icon-button"
                        href={downloadUrl(file.path)}
                        download
                        target="_blank"
                        rel="noreferrer"
                        aria-label={`${file.name} indir`}
                        title="Dosyayı indir"
                      >
                        <ArrowDownToLine size={17} />
                      </a>
                    </div>
                  </div>
                ))}
              </div>
            )}
            <div className="browser-footer">
              <span>
                <ShieldCheck size={14} /> Sadece size tanımlı dosyalar gösterilir
              </span>
              {listing.hasNextPage ? (
                <button
                  className="text-button"
                  disabled={listing.isFetchingNextPage}
                  onClick={() => void listing.fetchNextPage()}
                >
                  {listing.isFetchingNextPage ? 'Yükleniyor…' : 'Daha fazla yükle'}
                </button>
              ) : (
                <span>{folders.length + files.length} öğe</span>
              )}
            </div>
          </section>
          <div className="workspace-tip">
            <Table2 size={18} />
            <p>
              <strong>İndirmeden önce göz atın.</strong> CSV dosyalarındaki Önizle butonuyla
              verilerinizi doğrudan burada inceleyebilirsiniz.
            </p>
          </div>
          <footer className="page-footer">
            <span>TenantFiles · {me.customer.name}</span>
            <span>Dosyalarınız, sizin alanınız.</span>
          </footer>
        </main>
      </div>
      {preview && (
        <CsvPreview
          key={preview.path}
          file={preview}
          customerId={me.customer.id}
          onClose={() => setPreview(null)}
        />
      )}
    </div>
  );
}
