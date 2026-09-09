import { Layers3 } from 'lucide-react';

export function Brand({ light = false }: { light?: boolean }) {
  return (
    <div className={`brand ${light ? 'brand-light' : ''}`}>
      <span className="brand-icon">
        <Layers3 size={21} />
      </span>
      TenantFiles<span className="brand-dot">.</span>
    </div>
  );
}
