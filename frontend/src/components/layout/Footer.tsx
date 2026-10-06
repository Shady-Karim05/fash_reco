import React from 'react';
import { Cpu, Database, Search, Sparkles } from 'lucide-react';

export const Footer: React.FC = () => {
  return (
    <footer className="bg-sand-900 text-sand-300 pt-16 pb-12 border-t border-sand-800">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-10 pb-12 border-b border-sand-800">
          {/* Brand info */}
          <div className="md:col-span-2 space-y-4">
            <span className="font-serif text-2xl text-white tracking-widest font-light">
              ATELIER
            </span>
            <p className="text-sand-400 text-sm max-w-md leading-relaxed">
              State-of-the-art semantic fashion discovery powered by Sentence Transformers, FAISS dense
              retrieval, BM25 sparse ranking, and Reciprocal Rank Fusion.
            </p>
            <div className="flex items-center gap-3 pt-2 text-xs text-sand-400">
              <span className="inline-flex items-center gap-1">
                <Database className="w-3.5 h-3.5 text-accent-400" />
                24,000 Catalog Items
              </span>
              <span>•</span>
              <span className="inline-flex items-center gap-1">
                <Cpu className="w-3.5 h-3.5 text-accent-400" />
                Hybrid RRF Ranking
              </span>
            </div>
          </div>

          {/* Microservice Architecture */}
          <div>
            <h4 className="text-white text-xs font-semibold uppercase tracking-wider mb-4">
              Microservice Core
            </h4>
            <ul className="space-y-2 text-xs text-sand-400">
              <li className="flex items-center gap-2">
                <Search className="w-3 h-3 text-sand-500" />
                Dense Vector FAISS
              </li>
              <li className="flex items-center gap-2">
                <Sparkles className="w-3 h-3 text-sand-500" />
                BM25 Okapi Sparse Search
              </li>
              <li className="flex items-center gap-2">
                <Cpu className="w-3 h-3 text-sand-500" />
                FastAPI Python Engine
              </li>
              <li className="flex items-center gap-2">
                <Database className="w-3 h-3 text-sand-500" />
                SQLite Catalog Store
              </li>
            </ul>
          </div>

          {/* Endpoints */}
          <div>
            <h4 className="text-white text-xs font-semibold uppercase tracking-wider mb-4">
              Backend Endpoints
            </h4>
            <ul className="space-y-2 text-xs font-mono text-sand-400">
              <li>GET /health</li>
              <li>POST /search</li>
              <li>POST /outfit</li>
              <li>GET /metrics</li>
            </ul>
          </div>
        </div>

        <div className="pt-8 flex flex-col sm:flex-row items-center justify-between text-xs text-sand-500 gap-4">
          <p>© {new Date().getFullYear()} Semantic Fashion Search & Recommendation System.</p>
          <p>Strict decoupled client architecture.</p>
        </div>
      </div>
    </footer>
  );
};
