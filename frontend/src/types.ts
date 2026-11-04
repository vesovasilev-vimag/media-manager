export interface Identity {
  title: string;
  year: number;
  media_type: string;
  provider_id?: string | null;
  edition?: string;
  season?: number | null;
  episodes?: number[];
  artist?: string;
  confirmed?: boolean;
  collection_override?: string;
  original_title?: string | null;
  original_name?: string | null;
  title_language?: string | null;
  english_title_verified?: boolean;
  title_provenance?: string | null;
  supplementary?: boolean;
  separate_edition?: boolean;
  collection_name?: string;
  collection_language?: string;
  collection_override_language?: string;
  episode_title?: string;
  episode_title_language?: string;
}
export interface ItemData {
  inspection?: {
    state: string;
    reason?: string;
    parsed?: { title: string; year?: number; media_type: string };
    proposed_identity?: Identity;
    candidates?: {
      id: string;
      title: string;
      year: number;
      media_type: string;
    }[];
  };
  identity?: Identity;
  source_name?: string;
  quality_label?: string;
  bg?: string;
  subtitle?: string;
  fingerprint?: string;
  probe?: {
    streams: Record<string, unknown>[];
    format?: { duration?: string };
  };
  candidates?: Record<string, unknown>[];
  published?: boolean;
  integrity?: boolean;
  [key: string]: unknown;
}
export interface Item {
  id: string;
  item_key?: string;
  data: ItemData;
}
export interface Job {
  id: string;
  kind: string;
  state: string;
  step: number;
  revision: number;
  paused: boolean;
  data: Record<string, unknown>;
  scope?: string;
  snapshot?: { category: string; save_path: string };
  media_items?: Item[];
  operations?: Operation[];
  timeline?: Audit[];
  created_at: string;
}
export interface Plan {
  id: string;
  job_id: string;
  revision: number;
  sha256: string;
  data: {
    entries?: { item_id: string; source_name: string; destination: string }[];
    source?: string;
    target?: string;
    strategy?: string;
    [key: string]: unknown;
  };
}
export interface Asset {
  id: string;
  relative_path: string;
  edition: string;
  fingerprint: string;
  data: ItemData & { dependencies?: string[] };
}
export interface Operation {
  id: string;
  job_id: string;
  kind: string;
  status: string;
  intent: Record<string, unknown>;
  observed?: Record<string, unknown>;
  created_at: string;
}
export interface Audit {
  id: string;
  kind: string;
  target?: string;
  actor: string;
  created_at: string;
  data: Record<string, unknown>;
}
export interface Evidence {
  id: string;
  item_id?: string;
  asset_id?: string;
  asset_revision?: number;
  data: Record<string, unknown>;
  context?: ItemData;
}
export interface Health {
  database: boolean;
  schema: string;
  write_enabled: boolean;
  automatic_intake: boolean;
  production_authorized?: boolean;
  worker: Record<string, unknown>;
}
