import { provideHttpClient } from '@angular/common/http';
import { bootstrapApplication } from '@angular/platform-browser';
import { Geomind } from './app/geomind/geomind';

bootstrapApplication(Geomind, {
  providers: [provideHttpClient()],
}).catch((err) => console.error(err));
