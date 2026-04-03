import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private http = inject(HttpClient);
  private base = 'http://localhost:5003';

  get<T>(path: string): Observable<T> {
    return this.http.get<T>(`${this.base}${path}`);
  }

  post<T>(path: string, body: any): Observable<T> {
    return this.http.post<T>(`${this.base}${path}`, body);
  }

  // Legacy dashboard endpoints
  status() { return this.get<any>('/api/status'); }
  extraction() { return this.get<any>('/api/extraction'); }
  deposits() { return this.get<any>('/api/deposits'); }
  compliance() { return this.get<any>('/api/compliance'); }
  deficiency() { return this.get<any>('/api/deficiency'); }
  coverage() { return this.get<any>('/api/coverage'); }
  runScript(name: string) { return this.post<any>(`/api/run/${name}`, {}); }

  // Core engine endpoints
  engineEntities() { return this.get<any>('/api/engine/entities'); }
  engineEntity(slug: string) { return this.get<any>(`/api/engine/entity/${slug}`); }
  engineAccounts(slug: string) { return this.get<any>(`/api/engine/accounts/${slug}`); }
  engineLedger(accountId: string, limit = 50) { return this.get<any>(`/api/engine/ledger/${accountId}?limit=${limit}`); }
  engineTrialBalance(slug: string) { return this.get<any>(`/api/engine/trial-balance/${slug}`); }
  engineCurrencies() { return this.get<any>('/api/engine/currencies'); }
  createEntity(data: any) { return this.post<any>('/api/engine/entity', data); }

  // Merit bridge
  meritBalance(project: string) { return this.get<any>(`/api/merit/balance/${project}`); }
  meritCanAfford(project: string, action: string, count = 1) {
    return this.get<any>(`/api/merit/can-afford/${project}?action=${action}&count=${count}`);
  }
  meritSpend(data: any) { return this.post<any>('/api/merit/spend', data); }
  meritCosts() { return this.get<any>('/api/merit/costs'); }

  // Resource management
  resourceMint(data: any) { return this.post<any>('/api/resources/mint', data); }
  resourceAllocate(data: any) { return this.post<any>('/api/resources/allocate', data); }
  resourceSpend(data: any) { return this.post<any>('/api/resources/spend', data); }
}
