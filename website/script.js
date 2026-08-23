// Configurações - SUBSTITUA PELOS DADOS DO SEU REPOSITÓRIO
const GITHUB_USER = 'LuizHenriqueFreitas';
const GITHUB_REPO = 'Free-Video-Downloader';
const CACHE_DURATION = 60 * 60 * 1000; // 1 hora em milissegundos

// URLs da API do GitHub
const REPO_URL = `https://api.github.com/repos/${GITHUB_USER}/${GITHUB_REPO}`;
const LATEST_RELEASE_URL = `${REPO_URL}/releases/latest`;
const ALL_RELEASES_URL = `${REPO_URL}/releases`;
const CONTRIBUTORS_URL = `${REPO_URL}/contributors`;

// Elementos do DOM
const downloadBtn = document.getElementById('downloadBtn');
const downloadCountEl = document.getElementById('downloadCount');
const versionTagEl = document.getElementById('versionTag');

// Elementos das estatísticas
const starsEl = document.querySelector('.stat-item i.fa-star')?.parentElement?.querySelector('span');
const contributorsEl = document.querySelector('.stat-item i.fa-code-branch')?.parentElement?.querySelector('span');
const lastUpdateEl = document.querySelector('.stat-item i.fa-clock')?.parentElement?.querySelector('span');

/**
 * Salva dados no cache local
 */
function saveToCache(key, data) {
    try {
        const cacheItem = {
            timestamp: Date.now(),
            data: data
        };
        localStorage.setItem(`github_cache_${key}`, JSON.stringify(cacheItem));
    } catch (error) {
        console.warn('Erro ao salvar cache:', error);
    }
}

/**
 * Busca dados do cache local
 */
function getFromCache(key) {
    try {
        const cached = localStorage.getItem(`github_cache_${key}`);
        if (!cached) return null;
        
        const cacheItem = JSON.parse(cached);
        const age = Date.now() - cacheItem.timestamp;
        
        // Verifica se o cache expirou
        if (age > CACHE_DURATION) {
            localStorage.removeItem(`github_cache_${key}`);
            return null;
        }
        
        return cacheItem.data;
    } catch (error) {
        console.warn('Erro ao ler cache:', error);
        return null;
    }
}

/**
 * Função genérica para fazer requisição com cache
 */
async function fetchWithCache(url, cacheKey) {
    // 1. Tenta buscar do cache
    const cachedData = getFromCache(cacheKey);
    if (cachedData) {
        console.log(`📦 Usando cache para: ${cacheKey}`);
        return cachedData;
    }
    
    // 2. Se não tem cache ou expirou, faz a requisição
    try {
        console.log(`🌐 Buscando dados da API: ${cacheKey}`);
        const response = await fetch(url);
        
        if (!response.ok) {
            throw new Error(`Erro HTTP: ${response.status}`);
        }
        
        const data = await response.json();
        
        // 3. Salva no cache
        saveToCache(cacheKey, data);
        
        return data;
    } catch (error) {
        console.error(`Erro ao buscar ${cacheKey}:`, error);
        return null;
    }
}

/**
 * Busca dados do repositório (estrelas, forks, etc)
 */
async function fetchRepoData() {
    return await fetchWithCache(REPO_URL, 'repo_data');
}

/**
 * Busca TODAS as releases do repositório
 */
async function fetchAllReleases() {
    // Tenta buscar do cache primeiro
    const cachedReleases = getFromCache('all_releases');
    if (cachedReleases) {
        console.log('📦 Usando cache para: all_releases');
        return cachedReleases;
    }
    
    // Se não tem cache, faz a requisição paginada
    try {
        console.log('🌐 Buscando todas as releases da API');
        let allReleases = [];
        let page = 1;
        let hasMore = true;
        
        while (hasMore) {
            const url = `${ALL_RELEASES_URL}?page=${page}&per_page=100`;
            const response = await fetch(url);
            
            if (!response.ok) {
                throw new Error(`Erro HTTP: ${response.status}`);
            }
            
            const data = await response.json();
            
            if (data.length === 0) {
                hasMore = false;
            } else {
                allReleases = allReleases.concat(data);
                page++;
                
                const linkHeader = response.headers.get('Link');
                if (!linkHeader || !linkHeader.includes('rel="next"')) {
                    hasMore = false;
                }
            }
        }
        
        // Salva no cache
        saveToCache('all_releases', allReleases);
        
        return allReleases;
    } catch (error) {
        console.error('Erro ao buscar releases:', error);
        return null;
    }
}

/**
 * Busca a última release (para a versão e download)
 */
async function fetchLatestRelease() {
    return await fetchWithCache(LATEST_RELEASE_URL, 'latest_release');
}

/**
 * Busca os contribuidores do repositório
 */
async function fetchContributors() {
    return await fetchWithCache(CONTRIBUTORS_URL, 'contributors');
}

/**
 * Calcula o total de downloads de TODAS as releases
 */
function calculateTotalDownloadsAllReleases(releases) {
    if (!releases || releases.length === 0) return 0;
    
    let total = 0;
    
    releases.forEach(release => {
        if (release.assets) {
            release.assets.forEach(asset => {
                total += (asset.download_count || 0);
            });
        }
    });
    
    return total;
}

/**
 * Calcula o total de downloads de UMA release específica
 */
function calculateTotalDownloadsSingleRelease(releaseData) {
    if (!releaseData || !releaseData.assets) return 0;
    
    return releaseData.assets.reduce((total, asset) => {
        return total + (asset.download_count || 0);
    }, 0);
}

/**
 * Encontra o asset correto baseado em critérios
 */
function findCorrectAsset(assets) {
    if (!assets || assets.length === 0) return null;
    
    if (assets.length === 1) return assets[0];
    
    let windowsAsset = assets.find(asset => 
        asset.name.toLowerCase().includes('windows') ||
        asset.name.toLowerCase().includes('win') ||
        asset.name.toLowerCase().includes('.exe')
    );
    
    if (windowsAsset) return windowsAsset;
    
    let zipAsset = assets.find(asset => 
        asset.name.toLowerCase().endsWith('.zip')
    );
    
    if (zipAsset) return zipAsset;
    
    let nonSourceAsset = assets.find(asset => 
        !asset.name.toLowerCase().includes('source') &&
        !asset.name.toLowerCase().includes('src')
    );
    
    if (nonSourceAsset) return nonSourceAsset;
    
    return assets[0];
}

/**
 * Formata números grandes (ex: 1200 -> 1.2k)
 */
function formatNumber(num) {
    if (num >= 1000000) {
        return (num / 1000000).toFixed(1) + 'M';
    }
    if (num >= 1000) {
        return (num / 1000).toFixed(1) + 'k';
    }
    return num.toString();
}

/**
 * Formata a data de forma amigável
 */
function formatDate(dateString) {
    const date = new Date(dateString);
    const now = new Date();
    const diffTime = Math.abs(now - date);
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
    
    if (diffDays === 0) {
        return 'Hoje';
    } else if (diffDays === 1) {
        return 'Ontem';
    } else if (diffDays < 7) {
        return `${diffDays} dias atrás`;
    } else if (diffDays < 30) {
        const weeks = Math.floor(diffDays / 7);
        return `${weeks} ${weeks === 1 ? 'semana' : 'semanas'} atrás`;
    } else if (diffDays < 365) {
        const months = Math.floor(diffDays / 30);
        return `${months} ${months === 1 ? 'mês' : 'meses'} atrás`;
    } else {
        const years = Math.floor(diffDays / 365);
        return `${years} ${years === 1 ? 'ano' : 'anos'} atrás`;
    }
}

/**
 * Atualiza as estatísticas do repositório
 */
async function updateStats() {
    try {
        // Busca dados do repositório (estrelas e data de atualização)
        const repoData = await fetchRepoData();
        
        // Busca contribuidores
        const contributors = await fetchContributors();
        
        // Atualiza ESTRELAS
        if (repoData && starsEl) {
            const stars = repoData.stargazers_count || 0;
            starsEl.textContent = formatNumber(stars);
        }
        
        // Atualiza CONTRIBUIDORES
        if (contributors && contributorsEl) {
            // Conta apenas contribuidores que não são bots
            const realContributors = contributors.filter(c => c.type === 'User');
            contributorsEl.textContent = realContributors.length;
        }
        
        // Atualiza ÚLTIMA ATUALIZAÇÃO
        if (repoData && lastUpdateEl) {
            const lastUpdate = repoData.updated_at || repoData.pushed_at;
            if (lastUpdate) {
                lastUpdateEl.textContent = formatDate(lastUpdate);
            }
        }
        
    } catch (error) {
        console.error('Erro ao atualizar estatísticas:', error);
    }
}

/**
 * Atualiza a interface com os dados de download e versão
 */
async function updateDownloadUI() {
    try {
        // Busca TODAS as releases (para o total de downloads)
        const allReleases = await fetchAllReleases();
        
        // Busca a última release (para versão e link de download)
        const latestRelease = await fetchLatestRelease();
        
        if (!allReleases && !latestRelease) {
            // Tenta usar dados do cache mais antigo como fallback
            const fallbackReleases = getFromCache('all_releases');
            const fallbackLatest = getFromCache('latest_release');
            
            if (fallbackReleases) {
                const totalDownloads = calculateTotalDownloadsAllReleases(fallbackReleases);
                downloadCountEl.textContent = totalDownloads.toLocaleString('pt-BR');
            }
            
            if (fallbackLatest) {
                const version = fallbackLatest.tag_name || 'v1.0.0';
                versionTagEl.textContent = version;
                
                const asset = findCorrectAsset(fallbackLatest.assets);
                if (asset) {
                    downloadBtn.href = asset.browser_download_url;
                }
            }
            
            downloadBtn.innerHTML = '<i class="fas fa-exclamation-triangle"></i> Dados em cache (offline)';
            return;
        }
        
        // 1. Atualiza o TOTAL de downloads (todas as releases)
        let totalDownloads = 0;
        if (allReleases) {
            totalDownloads = calculateTotalDownloadsAllReleases(allReleases);
            downloadCountEl.textContent = totalDownloads.toLocaleString('pt-BR');
        } else if (latestRelease) {
            totalDownloads = calculateTotalDownloadsSingleRelease(latestRelease);
            downloadCountEl.textContent = totalDownloads.toLocaleString('pt-BR');
        }
        
        // 2. Atualiza a VERSÃO (última release)
        if (latestRelease) {
            const version = latestRelease.tag_name || 'v1.0.0';
            versionTagEl.textContent = version;
            
            // 3. Atualiza o BOTÃO DE DOWNLOAD (última release)
            const asset = findCorrectAsset(latestRelease.assets);
            
            if (asset) {
                downloadBtn.href = asset.browser_download_url;
                downloadBtn.classList.remove('btn-disabled');
                downloadBtn.innerHTML = `
                    <i class="fas fa-windows"></i>
                    Download para Windows (${asset.name})
                    <span class="btn-badge">Grátis</span>
                `;
            } else {
                downloadBtn.href = '#';
                downloadBtn.classList.add('btn-disabled');
                downloadBtn.innerHTML = '<i class="fas fa-exclamation-triangle"></i> Nenhum arquivo disponível';
            }
        }
        
    } catch (error) {
        console.error('Erro ao atualizar downloads:', error);
    }
}

/**
 * Verifica o status do cache e mostra no console
 */
function showCacheStatus() {
    console.log('📊 STATUS DO CACHE:');
    const keys = ['repo_data', 'all_releases', 'latest_release', 'contributors'];
    keys.forEach(key => {
        const cached = getFromCache(key);
        if (cached) {
            console.log(`  ✅ ${key}: em cache`);
        } else {
            console.log(`  ❌ ${key}: sem cache`);
        }
    });
}

/**
 * Inicializa a página
 */
async function init() {
    console.log('🚀 Inicializando Get Media Free...');
    
    // Mostra status do cache
    showCacheStatus();
    
    // Atualiza todas as informações
    await Promise.all([
        updateStats(),
        updateDownloadUI()
    ]);
    
    console.log('✅ Site carregado com sucesso!');
    console.log(`⏰ Cache expira em: ${CACHE_DURATION / 60000} minutos`);
    
    // Atualiza automaticamente a cada hora (quando o cache expira)
    setInterval(async () => {
        console.log('🔄 Atualizando dados...');
        await Promise.all([
            updateStats(),
            updateDownloadUI()
        ]);
    }, CACHE_DURATION);
}

// Aguarda o DOM carregar antes de iniciar
document.addEventListener('DOMContentLoaded', init);


















// ============================================
// VIDEO PLAYER EMBBED
// ============================================

// Configuração - Substitua pelos IDs dos seus vídeos
const VIDEO_CONFIG = {
    'VIDEO_ID_1': {
        title: 'Como baixar vídeos do YouTube',
        embed: 'https://www.youtube.com/embed/UBFU6iqUqi4'
    },
    'VIDEO_ID_2': {
        title: 'Baixando Reels e Tiktoks',
        embed: 'https://www.youtube.com/embed/UBFU6iqUqi4'
    },
    'VIDEO_ID_3': {
        title: 'Reportando bug e Erros',
        embed: 'https://www.youtube.com/embed/UBFU6iqUqi4'
    }
};

// Elementos do DOM
const modal = document.getElementById('videoModal');
const modalClose = document.querySelector('.modal-close');
const playerContainer = document.getElementById('videoPlayerContainer');

// Abre o modal com o vídeo
function openVideo(videoId) {
    const video = VIDEO_CONFIG[videoId];
    if (!video) return;

    // Limpa o container
    playerContainer.innerHTML = '';
    
    // Cria o iframe
    const iframe = document.createElement('iframe');
    iframe.src = video.embed;
    iframe.allow = 'accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture';
    iframe.allowFullscreen = true;
    iframe.title = video.title;
    
    // Adiciona ao container
    playerContainer.appendChild(iframe);
    
    // Mostra o modal
    modal.classList.add('active');
    document.body.style.overflow = 'hidden'; // Impede scroll
}

// Fecha o modal
function closeVideo() {
    modal.classList.remove('active');
    document.body.style.overflow = ''; // Restaura scroll
    
    // Para o vídeo removendo o iframe
    setTimeout(() => {
        playerContainer.innerHTML = '';
    }, 300);
}

// Event Listeners
document.querySelectorAll('.watch-btn').forEach(btn => {
    btn.addEventListener('click', function(e) {
        e.preventDefault();
        const videoId = this.dataset.videoId;
        if (videoId) {
            openVideo(videoId);
        }
    });
});

// Também funciona clicando no card (opcional)
document.querySelectorAll('.video-card').forEach(card => {
    card.addEventListener('click', function(e) {
        // Evita que o clique no botão dispare duas vezes
        if (e.target.closest('.watch-btn')) return;
        
        const videoId = this.dataset.videoId;
        if (videoId) {
            openVideo(videoId);
        }
    });
});

// Fecha ao clicar no X
modalClose.addEventListener('click', closeVideo);

// Fecha ao clicar fora do modal
modal.addEventListener('click', function(e) {
    if (e.target === this) {
        closeVideo();
    }
});

// Fecha com a tecla ESC
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape' && modal.classList.contains('active')) {
        closeVideo();
    }
});









// ============================================
// CARROSSEL DE SCREENSHOTS
// ============================================

class ScreenshotCarousel {
    constructor() {
        this.track = document.getElementById('carouselTrack');
        this.prevBtn = document.getElementById('carouselPrev');
        this.nextBtn = document.getElementById('carouselNext');
        this.indicators = document.getElementById('carouselIndicators');
        this.slides = this.track.querySelectorAll('.carousel-slide');
        this.currentSlide = 0;
        this.totalSlides = this.slides.length;
        this.autoPlayInterval = null;
        this.autoPlayDelay = 5000; // 5 segundos
        this.isTransitioning = false;

        this.init();
    }

    init() {
        // Cria os indicadores (dots)
        this.createIndicators();
        
        // Adiciona event listeners
        this.prevBtn.addEventListener('click', () => this.prevSlide());
        this.nextBtn.addEventListener('click', () => this.nextSlide());
        
        // Navegação por teclado
        document.addEventListener('keydown', (e) => {
            if (e.key === 'ArrowLeft') this.prevSlide();
            if (e.key === 'ArrowRight') this.nextSlide();
        });
        
        // Pausa autoplay ao passar o mouse
        this.track.addEventListener('mouseenter', () => this.pauseAutoPlay());
        this.track.addEventListener('mouseleave', () => this.startAutoPlay());
        
        // Touch events para mobile
        let touchStartX = 0;
        let touchEndX = 0;
        
        this.track.addEventListener('touchstart', (e) => {
            touchStartX = e.changedTouches[0].screenX;
        }, { passive: true });
        
        this.track.addEventListener('touchend', (e) => {
            touchEndX = e.changedTouches[0].screenX;
            this.handleSwipe(touchStartX, touchEndX);
        }, { passive: true });
        
        // Inicia o autoplay
        this.startAutoPlay();
        
        // Atualiza a primeira posição
        this.updateCarousel();
    }

    createIndicators() {
        for (let i = 0; i < this.totalSlides; i++) {
            const dot = document.createElement('button');
            dot.className = 'carousel-dot';
            dot.setAttribute('aria-label', `Ir para slide ${i + 1}`);
            dot.dataset.index = i;
            dot.addEventListener('click', () => this.goToSlide(i));
            this.indicators.appendChild(dot);
        }
    }

    updateCarousel() {
        // Atualiza a posição do track
        this.track.style.transform = `translateX(-${this.currentSlide * 100}%)`;
        
        // Atualiza os dots
        const dots = this.indicators.querySelectorAll('.carousel-dot');
        dots.forEach((dot, index) => {
            dot.classList.toggle('active', index === this.currentSlide);
        });
    }

    goToSlide(index) {
        if (this.isTransitioning || index === this.currentSlide) return;
        if (index < 0) index = this.totalSlides - 1;
        if (index >= this.totalSlides) index = 0;
        
        this.isTransitioning = true;
        this.currentSlide = index;
        this.updateCarousel();
        
        setTimeout(() => {
            this.isTransitioning = false;
        }, 500);
    }

    nextSlide() {
        this.goToSlide(this.currentSlide + 1);
    }

    prevSlide() {
        this.goToSlide(this.currentSlide - 1);
    }

    handleSwipe(startX, endX) {
        const threshold = 50; // Distância mínima para considerar um swipe
        const diff = startX - endX;
        
        if (Math.abs(diff) > threshold) {
            if (diff > 0) {
                this.nextSlide();
            } else {
                this.prevSlide();
            }
        }
    }

    startAutoPlay() {
        if (this.autoPlayInterval) return;
        this.autoPlayInterval = setInterval(() => {
            this.nextSlide();
        }, this.autoPlayDelay);
    }

    pauseAutoPlay() {
        if (this.autoPlayInterval) {
            clearInterval(this.autoPlayInterval);
            this.autoPlayInterval = null;
        }
    }
}

// Inicializa o carrossel quando o DOM estiver carregado
document.addEventListener('DOMContentLoaded', () => {
    // Verifica se o carrossel existe na página
    if (document.getElementById('carouselTrack')) {
        new ScreenshotCarousel();
    }
});