import { useState, type FormEvent } from 'react';
import { ArrowRight, Check, KeyRound, LockKeyhole, ShieldCheck } from 'lucide-react';
import { api, errorMessage, type Me } from '../api';
import { Brand } from './Brand';

export function Login({ onLogin }: { onLogin: (me: Me) => void }) {
  const [key, setKey] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      // Anahtar yalnızca giriş isteğinde kullanılır; localStorage/sessionStorage'a yazılmaz.
      await api('/auth/login', { method: 'POST', body: JSON.stringify({ api_key: key.trim() }) });
      setKey('');
      onLogin(await api<Me>('/me'));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setKey('');
      setBusy(false);
    }
  }

  return (
    <main className="login-layout">
      <section className="login-story">
        <Brand light />
        <div className="story-content">
          <span className="eyebrow light">VERİLERİNİZ. SİZE ÖZEL.</span>
          <h1>
            Dosyalarınıza açılan
            <br />
            <em>güvenli bir alan.</em>
          </h1>
          <p>
            Raporlarınıza ulaşın, verilerinizi inceleyin.
            <br />
            İhtiyacınız olan her şey, tek bir yerde.
          </p>
          <div className="story-preview">
            <div className="preview-dots">
              <i />
              <i />
              <i />
              <span>Çalışma alanınız</span>
              <LockKeyhole size={13} />
            </div>
            <div className="tree-row">
              <span className="tree-dot" />
              Müşteri alanı
              <ShieldCheck size={16} />
            </div>
            <div className="tree-branch">
              <div>2026</div>
              <div className="tree-month">09 · Eylül</div>
              <div className="tree-site">
                <span>berlin_solar</span>
                <span>CSV</span>
              </div>
            </div>
            <div className="preview-note">
              <Check size={14} /> Yalnızca sizin erişiminiz için
            </div>
          </div>
        </div>
        <div className="story-footer">
          <ShieldCheck size={16} /> Size özel erişim. Kontrollü paylaşım.
        </div>
      </section>
      <section className="login-form-side">
        <span className="login-topline">
          MÜŞTERİ PORTALI <span>01 / GİRİŞ</span>
        </span>
        <div className="login-form-wrap">
          <div className="login-key">
            <KeyRound size={24} />
          </div>
          <span className="eyebrow">HOŞ GELDİNİZ</span>
          <h2>Çalışma alanınıza giriş yapın</h2>
          <p>
            Yöneticinizin paylaştığı API anahtarıyla
            <br className="desktop-break" /> dosyalarınıza güvenle erişin.
          </p>
          <form onSubmit={submit}>
            <label htmlFor="api-key">API anahtarınız</label>
            <div className="key-field">
              <KeyRound size={18} />
              <input
                id="api-key"
                type="password"
                value={key}
                onChange={(e) => setKey(e.target.value)}
                placeholder="tf_••••••••.••••••••"
                autoComplete="off"
                spellCheck={false}
                required
                maxLength={100}
                disabled={busy}
                aria-describedby="key-help"
              />
            </div>
            <p id="key-help" className="input-hint">
              <LockKeyhole size={13} /> Anahtarınız bu tarayıcıda kalıcı olarak saklanmaz.
            </p>
            {error && (
              <div role="alert" className="error-box">
                {error}
              </div>
            )}
            <button className="primary login-submit" disabled={busy || !key.trim()}>
              {busy ? 'Giriş yapılıyor…' : 'Güvenli giriş yap'}
              <ArrowRight size={18} />
            </button>
          </form>
          <div className="login-help">
            Henüz bir anahtarınız yok mu?
            <br />
            <strong>Hesap yöneticinizden erişim isteyin.</strong>
          </div>
        </div>
        <footer className="login-bottom">
          <span>TenantFiles müşteri portalı</span>
          <span>
            <LockKeyhole size={13} /> Kişiye özel erişim
          </span>
        </footer>
      </section>
    </main>
  );
}
