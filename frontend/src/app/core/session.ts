import { Injectable, inject, signal } from '@angular/core';
import { HttpClient, HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { CanActivateFn, Router } from '@angular/router';
import { catchError, firstValueFrom, throwError, timeout } from 'rxjs';

@Injectable({providedIn:'root'})
export class Session {
  private http = inject(HttpClient);
  private attempt=0;
  readonly token = signal<string|null>(null);
  readonly notice = signal('');
  readonly challenge = signal<string|null>(null);
  async login(email:string, password:string):Promise<void> {
    const attempt=++this.attempt;this.challenge.set(null);
    const result = await firstValueFrom(this.http.post<{access_token?:string;challenge_token?:string;mfa_required?:boolean}>('/api/v1/auth/login',{email,password}).pipe(timeout(15000)));
    if(attempt!==this.attempt)throw new Error('Authentication cancelled');
    this.notice.set(''); this.token.set(result.access_token || null); this.challenge.set(result.mfa_required ? result.challenge_token || null : null);
  }
  clear(message=''):void {this.attempt++;this.challenge.set(null);this.token.set(null); this.notice.set(message);}
  async completeMfa(code:string):Promise<void> {
    const attempt=this.attempt,challenge=this.challenge();if(!challenge)throw new Error('Missing challenge');
    const result=await firstValueFrom(this.http.post<{access_token:string}>('/api/v1/auth/mfa/login',{challenge_token:challenge,code}).pipe(timeout(15000)));
    if(attempt!==this.attempt || this.challenge()!==challenge)throw new Error('Authentication cancelled');
    this.challenge.set(null);this.token.set(result.access_token);
  }
  async logout():Promise<void> {
    await firstValueFrom(this.http.post('/api/v1/auth/logout',{}).pipe(timeout(15000)));
    this.clear();
  }
}
export const authGuard:CanActivateFn = () => inject(Session).token() ? true : inject(Router).createUrlTree(['/login']);
export const sessionInterceptor:HttpInterceptorFn = (request,next) => {
  const session=inject(Session), token=session.token();
  const ownApi=request.url.startsWith('/api/v1/');
  const outgoing=ownApi && token ? request.clone({setHeaders:{Authorization:`Bearer ${token}`}}) : request;
  return next(outgoing).pipe(catchError((error:unknown) => {
    if(ownApi && token && error instanceof HttpErrorResponse && error.status===401 && session.token()===token) {
      session.clear('Sua sessão expirou ou foi encerrada. Entre novamente.');
    }
    return throwError(() => error);
  }));
};
export function errorMessage(error:unknown):string {
  if(error instanceof HttpErrorResponse) {
    if(error.status===401) return 'E-mail ou senha inválidos, ou sessão encerrada.';
    if(error.status===403 || error.status===404) return 'Este recurso não está disponível para seu acesso. Atualize a seleção de empresa.';
    if(error.status===409) return 'Os dados foram alterados ou a operação não é compatível com o estado atual. Atualize antes de continuar.';
    if(error.status===422) return 'Confira os campos e as datas informadas.';
    if(error.status===429) return 'Muitas tentativas. Aguarde antes de tentar novamente.';
  }
  return 'Não foi possível concluir a solicitação. Verifique sua conexão e tente novamente.';
}
