import { Injectable, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom, timeout } from 'rxjs';

@Injectable({providedIn:'root'})
export class AccountApi {
  private http=inject(HttpClient);
  readonly capabilities=signal({email_flows_available:false,mfa_enrollment_available:false});
  async load():Promise<void>{
    this.capabilities.set(await firstValueFrom(this.http.get<{email_flows_available:boolean;mfa_enrollment_available:boolean}>('/api/v1/auth/capabilities').pipe(timeout(15000))));
  }
  async post<T={detail:string}>(path:string,body:unknown):Promise<T>{
    return firstValueFrom(this.http.post<T>('/api/v1/auth/'+path,body).pipe(timeout(15000)));
  }
}
