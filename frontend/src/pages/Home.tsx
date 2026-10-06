import React from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Sparkles,
  ArrowRight,
  ShieldCheck,
  Zap,
  Compass,
  Search,
  CheckCircle2,
} from 'lucide-react';
import { SearchBar } from '../components/common/SearchBar';
import { Button } from '../components/common/Button';

export const Home: React.FC = () => {
  const navigate = useNavigate();

  const handleSearch = (query: string) => {
    navigate(`/search?q=${encodeURIComponent(query)}`);
  };

  const curatedCollections = [
    {
      title: 'Haute Evening & Gala',
      query: 'red cocktail dress',
      desc: 'Sculpted silhouettes, structured silk, and dramatic necklines for black-tie affairs',
      tag: 'Trending Now',
      colorBadge: 'bg-rose-50 text-rose-800 border-rose-200',
    },
    {
      title: 'Summer Riviera Linen',
      query: 'oversized linen blazer for summer',
      desc: 'Effortless tailoring, airy natural weaves, and refined ecru palettes for sunlit escapes',
      tag: 'Seasonal Edit',
      colorBadge: 'bg-amber-50 text-amber-800 border-amber-200',
    },
    {
      title: 'Technical Minimalist',
      query: 'black waterproof running shoes',
      desc: 'Streamlined monochromatic footwear engineered for high-performance city movement',
      tag: 'Athletic Luxury',
      colorBadge: 'bg-stone-100 text-stone-800 border-stone-200',
    },
    {
      title: 'Artisanal Leather',
      query: 'vintage leather crossbody bag',
      desc: 'Hand-finished accessories crafted with rich patina and architectural hardware',
      tag: 'Timeless Icons',
      colorBadge: 'bg-orange-50 text-orange-800 border-orange-200',
    },
  ];

  const categoryCapsules = [
    { label: 'Dresses & Gowns', query: 'cocktail evening dresses', count: '4,200+' },
    { label: 'Tailored Tops', query: 'silk blouses and structured shirts', count: '6,100+' },
    { label: 'Bottoms & Trousers', query: 'pleated trousers and wide leg pants', count: '3,800+' },
    { label: 'Luxury Footwear', query: 'leather boots and classic heels', count: '5,400+' },
    { label: 'Accessories & Bags', query: 'designer jewelry and leather handbags', count: '4,500+' },
  ];

  return (
    <div className="space-y-28 pb-28">
      {/* Editorial Luxury Hero Section */}
      <section className="relative overflow-hidden pt-20 pb-28 md:pt-28 md:pb-36 border-b border-sand-200/80 bg-gradient-to-b from-white via-sand-50/40 to-sand-50/80">
        {/* Soft Ambient Glow Elements */}
        <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-[850px] h-[400px] bg-gradient-to-tr from-accent-200/30 via-sand-200/25 to-transparent blur-3xl -z-10 pointer-events-none" />
        <div className="absolute top-10 right-10 w-96 h-96 bg-brand-200/15 rounded-full blur-3xl -z-10 pointer-events-none" />

        <div className="max-w-4xl mx-auto px-4 sm:px-6 text-center space-y-8">
          <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-white/90 border border-sand-200 text-xs font-semibold uppercase tracking-[0.2em] text-brand-900 shadow-xs backdrop-blur-xs">
            <Sparkles className="w-3.5 h-3.5 text-accent-600 animate-pulse" />
            <span>Neural Vector & Lexical Hybrid Search</span>
          </div>

          <h1 className="font-serif text-4xl sm:text-6xl md:text-7xl font-normal tracking-tight text-brand-900 leading-[1.08]">
            Fashion Discovered by <span className="italic font-light">Mood</span>,{' '}
            <span className="italic font-light">Silhouette</span> & Context
          </h1>

          <p className="max-w-2xl mx-auto text-base sm:text-lg text-sand-600 leading-relaxed font-light">
            Transcend keyword matching. Our AI engine comprehends aesthetic vibes, occasions,
            palette nuances, and budget constraints across 24,000 verified apparel pieces.
          </p>

          {/* Luxury Semantic Search Input */}
          <div className="max-w-2xl mx-auto pt-3">
            <div className="p-1 rounded-full bg-white/95 shadow-premium border border-sand-200 hover:border-sand-300 transition-all duration-300">
              <SearchBar
                placeholder="Search by mood, cut, color, or occasion (e.g. 'red cocktail dress')..."
                onSearch={handleSearch}
                size="lg"
                showPills={true}
                examplePills={[
                  'red cocktail dress',
                  'summer linen blazer',
                  'waterproof running shoes',
                  'vintage leather bag',
                  'women formal party outfit',
                ]}
              />
            </div>
          </div>

          {/* Primary Action Button */}
          <div className="pt-4 flex items-center justify-center">
            <Button
              variant="primary"
              size="lg"
              onClick={() => navigate('/search')}
              icon={<Compass className="w-4 h-4 text-accent-300" />}
              className="px-8 shadow-md hover:shadow-lg hover:-translate-y-0.5 transition-all"
            >
              Explore Full Collection
            </Button>
          </div>

          {/* Trust & Architecture Metrics Strip */}
          <div className="pt-10 grid grid-cols-2 sm:grid-cols-4 gap-4 max-w-3xl mx-auto border-t border-sand-200/70">
            <div className="text-center p-3 rounded-2xl bg-white/60 border border-sand-100">
              <div className="font-serif text-xl sm:text-2xl font-normal text-brand-900">24,000+</div>
              <div className="text-[11px] uppercase tracking-wider text-sand-500 font-medium mt-0.5">
                Curated Products
              </div>
            </div>
            <div className="text-center p-3 rounded-2xl bg-white/60 border border-sand-100">
              <div className="font-serif text-xl sm:text-2xl font-normal text-brand-900">&lt; 50ms</div>
              <div className="text-[11px] uppercase tracking-wider text-sand-500 font-medium mt-0.5">
                Search Latency
              </div>
            </div>
            <div className="text-center p-3 rounded-2xl bg-white/60 border border-sand-100">
              <div className="font-serif text-xl sm:text-2xl font-normal text-brand-900">100%</div>
              <div className="text-[11px] uppercase tracking-wider text-sand-500 font-medium mt-0.5">
                Top-1 Relevance
              </div>
            </div>
            <div className="text-center p-3 rounded-2xl bg-white/60 border border-sand-100">
              <div className="font-serif text-xl sm:text-2xl font-normal text-brand-900">Zero</div>
              <div className="text-[11px] uppercase tracking-wider text-sand-500 font-medium mt-0.5">
                Budget Violations
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Quick Category Capsules Bar */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="bg-white/80 backdrop-blur-md rounded-3xl p-6 sm:p-8 border border-sand-200/90 shadow-subtle">
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 mb-6">
            <div>
              <span className="text-[10px] uppercase tracking-[0.2em] font-semibold text-accent-700">
                Department Navigation
              </span>
              <h3 className="font-serif text-2xl text-brand-900 font-light mt-0.5">
                Browse by Category
              </h3>
            </div>
            <button
              onClick={() => navigate('/search')}
              className="text-xs uppercase tracking-wider font-semibold text-brand-900 hover:text-black flex items-center gap-1 group"
            >
              <span>View All</span>
              <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-1 transition-transform" />
            </button>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3.5">
            {categoryCapsules.map((cat, idx) => (
              <button
                key={idx}
                type="button"
                onClick={() => handleSearch(cat.query)}
                className="group p-4 rounded-2xl bg-sand-50/70 hover:bg-brand-900 border border-sand-200 hover:border-brand-900 transition-all duration-300 text-left hover:-translate-y-1 hover:shadow-md flex flex-col justify-between"
              >
                <span className="text-sm font-medium text-brand-900 group-hover:text-white transition-colors">
                  {cat.label}
                </span>
                <span className="text-[11px] text-sand-500 group-hover:text-sand-300 font-mono mt-3 transition-colors">
                  {cat.count} items
                </span>
              </button>
            ))}
          </div>
        </div>
      </section>

      {/* Curated Semantic Lookbooks */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 space-y-10">
        <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4 border-b border-sand-200 pb-5">
          <div>
            <span className="text-xs uppercase tracking-[0.2em] font-semibold text-accent-700">
              Inspiration & Intent
            </span>
            <h2 className="font-serif text-3xl sm:text-4xl font-light text-brand-900 mt-1">
              Curated Style Aesthetics
            </h2>
          </div>
          <button
            onClick={() => navigate('/search')}
            className="text-xs uppercase tracking-widest font-semibold text-brand-900 hover:text-black flex items-center gap-1.5 group"
          >
            <span>Explore Entire Catalog</span>
            <ArrowRight className="w-3.5 h-3.5 transition-transform group-hover:translate-x-1" />
          </button>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-7">
          {curatedCollections.map((col, idx) => (
            <div
              key={idx}
              onClick={() => handleSearch(col.query)}
              className="group bg-white rounded-3xl p-6.5 border border-sand-200/90 shadow-subtle hover:shadow-premium hover:-translate-y-1.5 transition-all duration-400 flex flex-col justify-between cursor-pointer"
            >
              <div className="space-y-3.5">
                <span
                  className={`inline-block text-[10px] uppercase tracking-wider font-semibold px-2.5 py-1 rounded-full border ${col.colorBadge}`}
                >
                  {col.tag}
                </span>
                <h3 className="font-serif text-2xl text-brand-900 group-hover:text-black transition-colors">
                  {col.title}
                </h3>
                <p className="text-xs text-sand-600 leading-relaxed font-sans">{col.desc}</p>
              </div>

              <div className="pt-6 border-t border-sand-100 mt-8 flex items-center justify-between">
                <span className="text-xs font-mono text-sand-500 font-medium">
                  &ldquo;{col.query}&rdquo;
                </span>
                <span className="w-8 h-8 rounded-full bg-sand-100 group-hover:bg-brand-900 group-hover:text-white flex items-center justify-center transition-colors text-sand-700 shadow-2xs">
                  <ArrowRight className="w-3.5 h-3.5" />
                </span>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Editorial AI Capabilities Showcase */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="bg-gradient-to-br from-brand-950 via-brand-900 to-black text-white rounded-3xl p-8 sm:p-14 md:p-16 shadow-2xl relative overflow-hidden border border-brand-800">
          <div className="relative z-10 max-w-3xl space-y-6">
            <div className="inline-flex items-center gap-2 text-xs uppercase tracking-[0.2em] px-3.5 py-1.5 rounded-full bg-white/10 text-sand-200 border border-white/15 backdrop-blur-xs font-medium">
              <Sparkles className="w-3.5 h-3.5 text-accent-300" />
              <span>Multi-Stage Intelligence</span>
            </div>

            <h2 className="font-serif text-3xl sm:text-5xl font-light leading-tight">
              Semantic Search Refined to Perfection
            </h2>

            <p className="text-sand-300 text-sm sm:text-base leading-relaxed">
              Every query passes through a multi-tier neural pipeline: Layer 1 fast extraction,
              Gemini Flash Lite intent understanding, FAISS dense vector similarity, and BM25 Okapi lexical
              scoring fused with Reciprocal Rank Fusion.
            </p>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-4">
              <div className="p-4 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-sm">
                <div className="flex items-center gap-2 text-accent-300 font-medium text-xs uppercase tracking-wider mb-1">
                  <CheckCircle2 className="w-4 h-4" />
                  <span>Precise Colors & Slots</span>
                </div>
                <p className="text-xs text-sand-400">
                  Strictly isolates garments by categories without cross-slot confusion.
                </p>
              </div>
              <div className="p-4 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-sm">
                <div className="flex items-center gap-2 text-accent-300 font-medium text-xs uppercase tracking-wider mb-1">
                  <CheckCircle2 className="w-4 h-4" />
                  <span>Budget Hard Filters</span>
                </div>
                <p className="text-xs text-sand-400">
                  Guaranteed budget compliance on price constraints (e.g. &apos;under $50&apos;).
                </p>
              </div>
              <div className="p-4 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-sm">
                <div className="flex items-center gap-2 text-accent-300 font-medium text-xs uppercase tracking-wider mb-1">
                  <CheckCircle2 className="w-4 h-4" />
                  <span>Bounded Caching</span>
                </div>
                <p className="text-xs text-sand-400">
                  0.02ms intent retrieval with normalized thread-safe LRU caching.
                </p>
              </div>
            </div>

            <div className="pt-4">
              <Button
                variant="secondary"
                size="lg"
                onClick={() => navigate('/search')}
                icon={<Search className="w-4 h-4" />}
                className="shadow-lg hover:shadow-xl hover:bg-white text-brand-900"
              >
                Try Semantic Search
              </Button>
            </div>
          </div>

          {/* Aesthetic background glow */}
          <div className="absolute -right-16 -bottom-16 w-[450px] h-[450px] bg-accent-500/15 rounded-full blur-3xl pointer-events-none" />
        </div>
      </section>

      {/* Engineering Highlights */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="bg-sand-100/50 rounded-3xl p-8 sm:p-12 border border-sand-200">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            <div className="flex items-start gap-4">
              <div className="w-11 h-11 rounded-2xl bg-white shadow-xs border border-sand-200 flex items-center justify-center text-accent-700 shrink-0">
                <Sparkles className="w-5 h-5" />
              </div>
              <div className="space-y-1.5">
                <h4 className="font-serif text-lg text-brand-900">Dense + Sparse Hybrid</h4>
                <p className="text-xs text-sand-600 leading-relaxed">
                  Blends Sentence Transformer dense vectors (FAISS) with BM25 Okapi lexical scoring
                  via calibrated Reciprocal Rank Fusion.
                </p>
              </div>
            </div>

            <div className="flex items-start gap-4">
              <div className="w-11 h-11 rounded-2xl bg-white shadow-xs border border-sand-200 flex items-center justify-center text-accent-700 shrink-0">
                <ShieldCheck className="w-5 h-5" />
              </div>
              <div className="space-y-1.5">
                <h4 className="font-serif text-lg text-brand-900">Deterministic Constraints</h4>
                <p className="text-xs text-sand-600 leading-relaxed">
                  Enforces strict filters for gender, slot type, and budget limits with circuit-breaker
                  resilience and zero failure fallbacks.
                </p>
              </div>
            </div>

            <div className="flex items-start gap-4">
              <div className="w-11 h-11 rounded-2xl bg-white shadow-xs border border-sand-200 flex items-center justify-center text-accent-700 shrink-0">
                <Zap className="w-5 h-5" />
              </div>
              <div className="space-y-1.5">
                <h4 className="font-serif text-lg text-brand-900">High Performance</h4>
                <p className="text-xs text-sand-600 leading-relaxed">
                  Sub-50ms hybrid retrieval across 24,000 apparel records with query normalization and
                  thread-safe LRU caching.
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
};
