" vimrc - vim 8 with native packages (:help packages). NOT self-contained: the
" plugins in vim/plugins.txt must be cloned into ~/.vim/pack/bundle/start/,
" which install.sh does. Nothing here hard-fails without them - a missing
" package is simply not loaded and the g:ale_* / g:airline_* settings sit unread.

filetype plugin indent on
packadd! comment " Vim's built-in gc / gcc / gcap commenting

let mapleader = " "

syntax on
set shiftwidth=4 "proper shiftwidth
set tabstop=4 " number of visual spaces per TAB
set showmatch " highlight matching [{()}]
set incsearch " search as characters are entered

" :grep through ripgrep when present - gitignore-aware, quickfix-ready output.
if executable('rg')
  set grepprg=rg\ --vimgrep
  set grepformat=%f:%l:%c:%m
endif
set hlsearch " highlight matches
set hidden
set ignorecase " smartcase needs it
set smartcase "For ignoring lowercase when search except when uppercase
" Try to put the indent level at the right place
set smartindent
set breakindent "wraps on same indent
" Keep vim files in the ~/.vim folder
set viminfo='100,h,n~/.vim/viminfo
" sets line number
set nu
set relativenumber
set display=truncate " Show @@@ only when line is truncated, not just at EOL

" Additive defaults (macOS-friendly)
set clipboard^=unnamed,unnamedplus

" Netrw cosmetics
let g:netrw_banner = 0
let g:netrw_liststyle = 3
set termguicolors
set scrolloff=5 sidescrolloff=8
set updatetime=300
set splitright splitbelow
set undofile
set undodir=~/.vim/undo//
set backupdir=~/.vim/backup//
set directory=~/.vim/swap//

" vim never creates these itself: a missing undodir silently drops persistent
" undo, and a missing directory/backupdir makes writes emit E303/E510.
for s:statedir in ['~/.vim/undo', '~/.vim/backup', '~/.vim/swap']
  if !isdirectory(expand(s:statedir))
    silent! call mkdir(expand(s:statedir), 'p', 0700)
  endif
endfor

augroup AutoSaveFolds
  autocmd!
  autocmd BufWinLeave ?* silent! mkview
  autocmd BufWinEnter ?* silent! loadview
augroup END

" Templates. The tracked skeletons carry a {{AUTHOR}} placeholder instead of a
" name, so a fork of this repo does not stamp its owner into every new file.
" Fill it in per machine, in ~/.vim/after/plugin/zz-local.vim:
"     let g:dotfiles_author = 'Your Name'
" Left unset, the placeholder is removed and the field is simply blank.
function! s:LoadTemplate(name) abort
  let l:path = expand('~/.vim/templates/' . a:name)
  if !filereadable(l:path)
    return
  endif
  execute '0r ' . fnameescape(l:path)
  " 'e' so a template with no placeholder is not an error. The replacement is
  " escaped because & and ~ are special on the right-hand side of :s.
  silent! execute '%s/{{AUTHOR}}/' . escape(get(g:, 'dotfiles_author', ''), '/\&~') . '/ge'
  call cursor(1, 1)
endfunction

augroup templates
  autocmd!
  autocmd BufNewFile *.cpp call <SID>LoadTemplate('skeleton.cpp')
  autocmd BufNewFile *.rmd call <SID>LoadTemplate('skeleton.rmd')
  autocmd BufNewFile *.rkt call <SID>LoadTemplate('skeleton.rkt')
  autocmd BufNewFile *.c   call <SID>LoadTemplate('skeleton.c')
  autocmd BufNewFile *.tex call <SID>LoadTemplate('skeleton.tex')
augroup END


nnoremap QQ :q!<CR>
inoremap ;; <Esc>/(++)<Enter>ca)
" Cost of the two mappings below, kept deliberately: both begin with 'c', so vim
" must wait out 'timeoutlen' (1000ms default) after every bare c before it can
" run the operator — cw, ci", cc all stall. <leader>clr / <leader>call (leader is
" space) would remove the delay without losing the commands.
nnoremap clr ggdG
nnoremap spc mtO<esc>jo<esc>`t
nnoremap call ggVG

" ALE settings. Inert without dense-analysis/ale —
" the variables just sit unread and SR reports an unknown command.
let g:ale_lint_on_text_changed = 'never'
nnoremap SR :ALEReset<CR>

" Airline. Inert without vim-airline; vim falls back to the built-in statusline.
let g:airline_section_z = '%l/%L  %p%%'

nmap WW :w<CR>

autocmd FileType python nnoremap <PageDown><PageDown> :w<CR>:!uv run %<CR>
autocmd FileType cpp nnoremap <PageDown><PageDown> :w<CR>:!g++ %:S -o a.out && ./a.out; rm -f a.out<CR>
autocmd FileType c   nnoremap <PageDown><PageDown> :w<CR>:!gcc %:S -o a.out && ./a.out; rm -f a.out<CR>
autocmd FileType markdown nnoremap <PageDown><PageDown> :w<CR>:!pandoc -f markdown -t latex -s -o %.pdf %<CR><CR>
autocmd Filetype markdown nnoremap <PageUp><PageUp> :put<space>=expand('%:p')<CR>A.pdf<esc>Iopen<space><esc>:.w<space>!bash<CR>
autocmd Filetype rmd nnoremap <PageDown><PageDown> :w<CR>:!echo<space>"require(rmarkdown);<space>render('<c-r>%')"<space>\|<space>R<space>--vanilla<CR>
autocmd Filetype rmd nnoremap <PageUp><PageUp> :put<space>=expand('%:p')<CR>A<esc>F.C.pdf<esc>Iopen<space><esc>:.w<space>!bash<CR>

autocmd Filetype tex      nnoremap <PageUp><PageUp> :put<space>=expand('%:p')<CR>A<esc>F.C.pdf<esc>Iopen<space><esc>:.w<space>!bash<CR><CR>dd
autocmd Filetype plaintex nnoremap <PageUp><PageUp> :put<space>=expand('%:p')<CR>A<esc>F.C.pdf<esc>Iopen<space><esc>:.w<space>!bash<CR><CR>dd

augroup tex_maps
  autocmd!
  autocmd FileType tex,plaintex inoremap ;it \item
  autocmd FileType tex,plaintex inoremap ;nls \begin{enumerate}<esc>yyplcwend<esc>O<tab>
  autocmd FileType tex,plaintex inoremap ;ls \begin{itemize}<esc>yyplcwend<esc>O<tab>
  autocmd FileType tex,plaintex inoremap ;td \todo[fancyline]{(++)}<esc>2hca)
  autocmd FileType tex,plaintex inoremap ;lr( \left( q \right)(++)<esc>Fqs
  autocmd FileType tex,plaintex inoremap ;tx  \text{}(++)<esc>F}i
  autocmd FileType tex,plaintex inoremap ;ds \displaystyle{}<esc>i
  autocmd FileType tex,plaintex nnoremap <PageDown><PageDown> :w<CR>:!xelatex -shell-escape %:S<CR><CR>
  autocmd FileType tex,plaintex inoremap <C-S-l> $$<esc>i
  autocmd FileType tex,plaintex inoremap ;sc \section{}<Esc>o<Tab>(++)<Esc>kf}i
  autocmd FileType tex,plaintex inoremap ;ssc \subsection{}<Esc>o<Tab>(++)<Esc>kf}i
  autocmd FileType tex,plaintex inoremap ;sssc \subsubsection{}<Esc>o<Tab>(++)<Esc>kf}i
  autocmd FileType tex,plaintex inoremap ;ssssc \subsubsubsection{}<Esc>o<Tab>(++)<Esc>kf}i
  autocmd FileType tex,plaintex inoremap ;beg \begin{}  %;zf to end <enter>\end{(++)}<Enter>(++)<esc>kO<tab>(++)<esc>k0f{a
  autocmd FileType tex,plaintex inoremap ;fr \frac{}{(++)}<esc>F\f}i
  " extension to the ;beg command:
  autocmd FileType tex,plaintex inoremap ;zf <esc>hhf}lDhh"tyi}2j0f{"tplda)<esc>2kA
augroup END

autocmd FileType rmd inoremap <C-S-l> $$<esc>i

nnoremap ;th :ThesaurusQueryReplaceCurrentWord<CR>

" Spellcheck prose only; in code buffers it flags identifiers and log strings.
augroup prose_spell
  autocmd!
  autocmd FileType markdown,rmd,tex,plaintex,gitcommit,text setlocal spell
augroup END
hi clear SpellBad
hi SpellBad cterm=underline
