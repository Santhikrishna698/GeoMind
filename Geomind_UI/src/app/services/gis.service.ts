import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

export const API_URL = 'http://localhost:8000';

export interface FeatureCollectionLike {
  type: string;
  features: any[];
}

export interface AskResponse {
  interpreted: any;
  clarification?: string | null;
  sql?: string;
  total?: number;
  returned?: number;
  geojson?: FeatureCollectionLike;
}

@Injectable({ providedIn: 'root' })
export class GisService {
  private http = inject(HttpClient);

  ask(text: string, location?: { lat: number; lon: number }): Observable<AskResponse> {
    return this.http.post<AskResponse>(`${API_URL}/api/ask`, { text, location });
  }

  getHealth(): Observable<any> {
    return this.http.get(`${API_URL}/api/health`);
  }

  getLayers(): Observable<any> {
    return this.http.get(`${API_URL}/api/layers`);
  }

  getLayerData(layerName: string, limit = 200): Observable<FeatureCollectionLike> {
    return this.http.get<FeatureCollectionLike>(`${API_URL}/api/data/${layerName}?limit=${limit}`);
  }
}