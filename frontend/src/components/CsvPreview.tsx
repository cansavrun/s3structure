import { useEffect, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Download, Table2, X } from 'lucide-react';
import { api, downloadUrl, errorMessage, formatBytes, type FileEntry, type Preview } from '../api';

export function CsvPreview({
  file,
  customerId,
  onClose,
}: {
  file: FileEntry;
  customerId: string;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const preview = useQuery({
    queryKey: ['preview', customerId, file.path],
    queryFn: ({ signal }) =>
      api<Preview>(`/files/preview?${new URLSearchParams({ path: file.path })}`, { signal }),
  });

  useEffect(() => {
    // Native dialog focus'u içinde tutar; Escape çalışır ve kapanınca önceki odak geri gelir.
    const dialog = ref.current!;
    dialog.showModal();
    return () => dialog.close();
  }, []);

  return (
    <dialog
      ref={ref}
      className="csv-dialog"
      aria-labelledby="preview-title"
      onCancel={onClose}
      onClick={(e) => {
        if (e.target === ref.current) onClose();
      }}
    >
      <div className="dialog-content">
        <header className="dialog-header">
          <div className="file-icon">
            <Table2 size={23} />
          </div>
          <div>
            <span className="eyebrow">CSV ÖNİZLEME</span>
            <h2 id="preview-title">{file.name}</h2>
            <p>{file.path}</p>
          </div>
          <button
            className="icon-button close-dialog"
            aria-label="Önizlemeyi kapat"
            onClick={onClose}
          >
            <X size={21} />
          </button>
        </header>
        <div className="preview-toolbar">
          <span>
            {formatBytes(file.size)}
            <span className="separator">/</span>
            {preview.data
              ? `${preview.data.headers.length} sütun · ${preview.data.rows.length} satır gösteriliyor`
              : 'Önizleme hazırlanıyor'}
          </span>
          <a
            className="secondary small"
            href={downloadUrl(file.path)}
            download
            target="_blank"
            rel="noreferrer"
          >
            <Download size={15} /> Dosyayı indir
          </a>
        </div>
        {preview.isPending ? (
          <div role="status" className="loading-state">
            <span className="spinner" /> CSV yükleniyor…
          </div>
        ) : preview.error ? (
          <div role="alert" className="error-box preview-error">
            {errorMessage(preview.error)}
            <button className="text-button" onClick={() => void preview.refetch()}>
              Tekrar dene
            </button>
          </div>
        ) : (
          preview.data && (
            <>
              <div className="csv-table-wrap">
                <table className="csv-table">
                  <thead>
                    <tr>
                      <th scope="col">#</th>
                      {preview.data.headers.map((header, i) => (
                        <th scope="col" key={i}>
                          {header || `Sütun ${i + 1}`}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {preview.data.rows.map((row, i) => (
                      <tr key={i}>
                        <th scope="row">{i + 1}</th>
                        {row.map((value, j) => (
                          <td key={j}>{value}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
                {!preview.data.headers.length && <p className="empty-state">Bu CSV dosyası boş.</p>}
              </div>
              <div className="dialog-footer">
                <span className="status-dot" />
                {preview.data.truncated
                  ? `İlk ${preview.data.row_limit} satır gösteriliyor. Tam veri için dosyayı indirin.`
                  : 'Önizleme salt okunurdur. Kaynak dosyada değişiklik yapılmaz.'}
              </div>
            </>
          )
        )}
      </div>
    </dialog>
  );
}
