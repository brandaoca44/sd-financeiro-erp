import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';

@Component({selector:'sdf-auth-frame',imports:[RouterLink],template:`
<main class="login-layout">
<svg class="auth-surface" viewBox="0 0 1800 1000" preserveAspectRatio="none" fill="none" aria-hidden="true"><defs><linearGradient id="auth-panel" x1="990" y1="400" x2="1800" y2="500" gradientUnits="userSpaceOnUse"><stop stop-color="#e1efff" stop-opacity=".52"/><stop offset=".26" stop-color="#f8fbff" stop-opacity=".90"/><stop offset=".72" stop-color="#fff" stop-opacity=".97"/><stop offset="1" stop-color="#dfebff" stop-opacity=".97"/></linearGradient></defs><path d="M1170-60C990 40 1090 335 977 510S860 769 700 1060H1860V-60Z" fill="url(#auth-panel)"/><path d="M1170-60C990 40 1090 335 977 510S860 769 700 1060" stroke="#d4ecff" stroke-width="1.3"/></svg>
<svg class="auth-wave auth-wave-bottom" viewBox="0 0 1800 320" preserveAspectRatio="none" fill="none" aria-hidden="true"><path d="M-50 40C260 60 300 270 750 280S1300 320 1850 80" stroke="#31b2fb" stroke-width="1.5"/>@for(offset of waveOffsets;track offset){<path [attr.transform]="'translate(0 '+offset+')'" d="M-50 40C260 60 300 270 750 280S1300 320 1850 80" stroke="#2397df" stroke-opacity=".17" stroke-width=".8"/>}</svg>
<svg class="auth-wave auth-wave-top" viewBox="0 0 600 250" fill="none" aria-hidden="true">@for(offset of waveOffsets;track offset){<path [attr.transform]="'translate(0 '+offset/2+')'" d="M-50-60C120-80 250 110 650 170" stroke="#598fe0" stroke-opacity=".19" stroke-width=".8"/>}</svg>
<section class="login-story" aria-label="Sistema Digital Financeiro"><a class="brand brand-light story-brand" routerLink="/login"><img class="brand-mark" src="/brand/sdf-mark.svg" alt="SDF" width="56" height="56"><span>Sistema Digital Financeiro<small>Gestão empresarial</small></span></a>
<div class="story-content"><span class="eyebrow light">PLATAFORMA DE GESTÃO EMPRESARIAL</span><h1>Sistema Digital<br>Financeiro</h1><p>Ambiente corporativo para administração financeira e controle das operações da empresa.</p><div class="institutional-scope">
<span><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="M3 21h18M5 18v-5h3v5m3 0V8h3v10m3 0V3h3v15M4 8l5-5 4 2 6-4"/></svg><strong>Gestão financeira</strong></span>
<span><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="m12 3 9 5-9 5-9-5 9-5Zm-9 9 9 5 9-5M3 16l9 5 9-5"/></svg><strong>Controle de obrigações</strong></span>
<span><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="M12 2 3 6v6c0 5 9 10 9 10s9-5 9-10V6l-9-4Z"/><path d="m7 12 3 3 7-7"/></svg><strong>Acessos e permissões</strong></span>
</div></div></section>
<section class="login-form-area"><a class="brand auth-brand" routerLink="/login"><img class="brand-mark" src="/brand/sdf-mark.svg" alt="SDF" width="56" height="56"><span>Sistema Digital Financeiro<small>Gestão empresarial</small></span></a><div class="login-form"><ng-content /></div></section></main>`})
export class AuthFrame {readonly waveOffsets=Array.from({length:22},(_,index)=>index*4);}
