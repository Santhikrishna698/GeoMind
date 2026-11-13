import { ComponentFixture, TestBed } from '@angular/core/testing';

import { Geomind } from './geomind';

describe('Geomind', () => {
  let component: Geomind;
  let fixture: ComponentFixture<Geomind>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [Geomind],
    }).compileComponents();

    fixture = TestBed.createComponent(Geomind);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
