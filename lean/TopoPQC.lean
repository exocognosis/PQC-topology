import Mathlib

/-!
# Topological Post-Quantum Cryptography Discovery — machine-checked results

Formalizes, for a single realization of the CRQC arrival time `T_Q`:

* Lemma 1 (exposure window): Mosca recovery, sunk part, remediable part, safe channels.
* Lemma 2 (windows under composition): hybrid and nested layers take the smaller window.
* Proposition 1 (dominance of propagated over local risk).
* Proposition 2 (monotonicity in every parameter).
* Proposition 3 (zero-risk characterization).
* Proposition 4 (least fixpoint of the propagation recurrence, constancy on strongly
  connected components, condensation recurrence).
* Expectation forms of Propositions 1–3 (Lebesgue integral over realizations).
* Proposition 6 (layer-cake identity) and Corollary 1 (hybrids with a finite
  post-quantum break time).
* Proposition 7 (session mixtures: share-weighted exposure for channels that negotiate
  several configurations).
* Proposition 8 (non-submodularity of worst-case risk reduction), by counterexample.

Break times live in `WithTop ℝ`; `⊤` is a channel that is never broken
(post-quantum or correctly bound hybrid layer).
-/

open Finset NNReal

namespace TopoPQC

/-! ## Exposure window (Definition 4) -/

/-- Exposure window for a finite break time `T`:
`W = [t_fix - max(-H, T - L)]⁺`. -/
noncomputable def W (tfix H L T : ℝ) : ℝ := max 0 (tfix - max (-H) (T - L))

/-- Exposure window for a possibly infinite break time. -/
noncomputable def Wb (tfix H L : ℝ) : WithTop ℝ → ℝ
  | none => 0
  | some T => W tfix H L T

@[simp] lemma Wb_top (tfix H L : ℝ) : Wb tfix H L ⊤ = 0 := rfl
@[simp] lemma Wb_coe (tfix H L T : ℝ) : Wb tfix H L (T : WithTop ℝ) = W tfix H L T := rfl

lemma W_nonneg (tfix H L T : ℝ) : 0 ≤ W tfix H L T := le_max_left _ _

lemma Wb_nonneg (tfix H L : ℝ) (T : WithTop ℝ) : 0 ≤ Wb tfix H L T := by
  induction T using WithTop.recTopCoe with
  | top => simp
  | coe t => simpa using W_nonneg tfix H L t

/-! ## Lemma 1 -/

/-- Lemma 1(1): with long enough history, the window is Mosca's slack `(L + t_fix - T)⁺`. -/
theorem lemma1_mosca (tfix H L T : ℝ) (h : -H ≤ T - L) :
    W tfix H L T = max 0 (L + tfix - T) := by
  unfold W
  rw [max_eq_right h]
  congr 1
  ring

/-- Lemma 1(1), inequality form: exposure is positive iff Mosca's `x + y > z`. -/
theorem lemma1_mosca_iff (tfix H L T : ℝ) (h : -H ≤ T - L) :
    0 < W tfix H L T ↔ T < L + tfix := by
  rw [lemma1_mosca tfix H L T h, lt_max_iff]
  constructor
  · rintro (h1 | h1)
    · exact absurd h1 (lt_irrefl 0)
    · linarith
  · intro h2
    right
    linarith

/-- Lemma 1(2): the sunk window (fix immediately) is `[min(H, L - T)]⁺`. -/
theorem lemma1_sunk (H L T : ℝ) : W 0 H L T = max 0 (min H (L - T)) := by
  unfold W
  rcases le_total (-H) (T - L) with h | h
  · rw [max_eq_right h, min_eq_right (by linarith)]
    congr 1
    ring
  · rw [max_eq_left h, min_eq_left (by linarith)]
    congr 1
    ring

/-- Lemma 1(3): the remediable part is `min(t_fix, W)`. -/
theorem lemma1_remediable (tfix H L T : ℝ) (ht : 0 ≤ tfix) :
    W tfix H L T - W 0 H L T = min tfix (W tfix H L T) := by
  unfold W
  set m := max (-H) (T - L)
  rcases le_or_gt m 0 with hm | hm
  · rw [max_eq_right (by linarith : (0 : ℝ) ≤ tfix - m),
      max_eq_right (by linarith : (0 : ℝ) ≤ 0 - m), min_eq_left (by linarith)]
    ring
  · rw [max_eq_left (by linarith : (0 : ℝ) - m ≤ 0), sub_zero,
      min_eq_right (max_le ht (by linarith))]

/-- Lemma 1(4): a channel that is never broken has zero window. -/
theorem lemma1_safe (tfix H L : ℝ) : Wb tfix H L ⊤ = 0 := rfl

/-- The window vanishes iff no history and no remaining exposure time,
or the break comes after the data stops being sensitive. -/
theorem W_eq_zero_iff (tfix H L T : ℝ) :
    W tfix H L T = 0 ↔ tfix + H ≤ 0 ∨ tfix + L ≤ T := by
  unfold W
  rw [max_eq_left_iff, sub_nonpos, le_max_iff]
  constructor
  · rintro (h | h)
    · left; linarith
    · right; linarith
  · rintro (h | h)
    · left; linarith
    · right; linarith

/-! ## Monotonicity of the window -/

lemma W_mono {tfix tfix' H H' L L' T T' : ℝ}
    (h1 : tfix ≤ tfix') (h2 : H ≤ H') (h3 : L ≤ L') (h4 : T' ≤ T) :
    W tfix H L T ≤ W tfix' H' L' T' := by
  unfold W
  apply max_le_max le_rfl
  apply sub_le_sub h1
  apply max_le_max (by linarith) (by linarith)

lemma Wb_mono {tfix tfix' H H' L L' : ℝ} {T T' : WithTop ℝ}
    (h1 : tfix ≤ tfix') (h2 : H ≤ H') (h3 : L ≤ L') (h4 : T' ≤ T) :
    Wb tfix H L T ≤ Wb tfix' H' L' T' := by
  induction T using WithTop.recTopCoe with
  | top => simpa using Wb_nonneg tfix' H' L' T'
  | coe t =>
    induction T' using WithTop.recTopCoe with
    | top => exact absurd h4 (WithTop.not_top_le_coe t)
    | coe t' =>
      simp only [Wb_coe]
      exact W_mono h1 h2 h3 (WithTop.coe_le_coe.mp h4)

/-! ## Lemma 2: windows under composition

Definition 3 composes break times with `max` (hybrid key establishment, nested
layers) and `min` (key establishment and bulk cipher within a layer). Because the
window is antitone in the break time, these become `min` and `max` of windows. -/

/-- Lemma 2(1): a component that breaks only when both parts break has the smaller
window. With `T₁ = T_Q` and `T₂ = T_PQ`, this is a hybrid key establishment whose
post-quantum part has a finite break time. -/
theorem lemma2_max (tfix H L : ℝ) (T₁ T₂ : WithTop ℝ) :
    Wb tfix H L (max T₁ T₂) = min (Wb tfix H L T₁) (Wb tfix H L T₂) := by
  rcases le_total T₁ T₂ with h | h
  · rw [max_eq_right h, min_eq_right (Wb_mono le_rfl le_rfl le_rfl h)]
  · rw [max_eq_left h, min_eq_left (Wb_mono le_rfl le_rfl le_rfl h)]

/-- Lemma 2(2): a component that breaks when either part breaks has the larger window. -/
theorem lemma2_min (tfix H L : ℝ) (T₁ T₂ : WithTop ℝ) :
    Wb tfix H L (min T₁ T₂) = max (Wb tfix H L T₁) (Wb tfix H L T₂) := by
  rcases le_total T₁ T₂ with h | h
  · rw [min_eq_left h, max_eq_left (Wb_mono le_rfl le_rfl le_rfl h)]
  · rw [min_eq_right h, max_eq_right (Wb_mono le_rfl le_rfl le_rfl h)]

/-- Lemma 2(3): a hybrid is never more exposed than either of its parts. -/
theorem lemma2_hybrid_le (tfix H L : ℝ) (T₁ T₂ : WithTop ℝ) :
    Wb tfix H L (max T₁ T₂) ≤ Wb tfix H L T₁ ∧ Wb tfix H L (max T₁ T₂) ≤ Wb tfix H L T₂ := by
  rw [lemma2_max]
  exact ⟨min_le_left _ _, min_le_right _ _⟩

/-! ## Channels and HNDL risk (Definition 5, one realization of `T_Q`) -/

/-- A channel: observability, remediation time, history, break time. -/
structure Channel where
  O : ℝ≥0
  tfix : ℝ
  H : ℝ
  T : WithTop ℝ

/-- Per-channel exposure `O(e) · W_e(d)`. -/
noncomputable def exposure (L : ℝ) (c : Channel) : ℝ≥0 :=
  c.O * (Wb c.tfix c.H L c.T).toNNReal

/-- Worst-case HNDL risk of a data class with criticality `C` and lifetime `L`
over the channel set `s`. -/
noncomputable def risk {ι : Type*} (C : ℝ≥0) (L : ℝ) (ch : ι → Channel) (s : Finset ι) : ℝ≥0 :=
  C * s.sup (fun e => exposure L (ch e))

variable {ι : Type*}

/-- Proposition 1 (dominance): risk over a superset of channels is at least
risk over a subset; in particular propagated risk ≥ local risk. -/
theorem prop1_dominance (C : ℝ≥0) (L : ℝ) (ch : ι → Channel) {s t : Finset ι}
    (h : s ⊆ t) : risk C L ch s ≤ risk C L ch t := by
  unfold risk
  exact mul_le_mul' le_rfl (Finset.sup_mono h)

/-- Channel order: more observable, later fix, longer history, earlier break. -/
def Channel.Le (c c' : Channel) : Prop :=
  c.O ≤ c'.O ∧ c.tfix ≤ c'.tfix ∧ c.H ≤ c'.H ∧ c'.T ≤ c.T

lemma exposure_mono {L L' : ℝ} {c c' : Channel} (hL : L ≤ L') (hc : c.Le c') :
    exposure L c ≤ exposure L' c' := by
  obtain ⟨hO, ht, hH, hT⟩ := hc
  unfold exposure
  exact mul_le_mul' hO (Real.toNNReal_le_toNNReal (Wb_mono ht hH hL hT))

/-- Proposition 2 (monotonicity): risk is non-decreasing in `C`, `L`, and in each
channel's observability, remediation time and history, non-increasing in each
break time, and non-decreasing when channels are added. -/
theorem prop2_monotone {C C' : ℝ≥0} {L L' : ℝ} {ch ch' : ι → Channel} {s t : Finset ι}
    (hC : C ≤ C') (hL : L ≤ L') (hch : ∀ e ∈ s, (ch e).Le (ch' e)) (hst : s ⊆ t) :
    risk C L ch s ≤ risk C' L' ch' t := by
  calc risk C L ch s ≤ risk C' L' ch' s := by
        unfold risk
        exact mul_le_mul' hC (Finset.sup_mono_fun fun e he => exposure_mono hL (hch e he))
    _ ≤ risk C' L' ch' t := prop1_dominance C' L' ch' hst

/-- Proposition 3 (zero risk). -/
theorem prop3_zero_iff (C : ℝ≥0) (L : ℝ) (ch : ι → Channel) (s : Finset ι) :
    risk C L ch s = 0 ↔
      C = 0 ∨ ∀ e ∈ s, (ch e).O = 0 ∨ Wb (ch e).tfix (ch e).H L (ch e).T = 0 := by
  unfold risk
  rw [mul_eq_zero]
  apply or_congr Iff.rfl
  rw [← nonpos_iff_eq_zero, Finset.sup_le_iff]
  apply forall₂_congr
  intro e _
  rw [nonpos_iff_eq_zero, exposure, mul_eq_zero, Real.toNNReal_eq_zero]
  apply or_congr Iff.rfl
  constructor
  · intro h; exact le_antisymm h (Wb_nonneg _ _ _ _)
  · intro h; exact h.le

/-- Proposition 3, safe-channel corollary: if every channel carrying the data class
has a layer that is never broken, the risk is zero. -/
theorem prop3_all_safe (C : ℝ≥0) (L : ℝ) (ch : ι → Channel) (s : Finset ι)
    (hsafe : ∀ e ∈ s, (ch e).T = ⊤) : risk C L ch s = 0 := by
  rw [prop3_zero_iff]
  right
  intro e he
  right
  rw [hsafe e he]
  rfl

/-- Proposition 3, finite-break-time form: a channel contributes zero iff it is
unobservable, has no history and no remaining exposure time, or breaks only
after `t_fix + L`. -/
theorem prop3_channel_zero_iff (L : ℝ) (O : ℝ≥0) (tfix H T : ℝ) :
    exposure L ⟨O, tfix, H, (T : WithTop ℝ)⟩ = 0 ↔ O = 0 ∨ tfix + H ≤ 0 ∨ tfix + L ≤ T := by
  rw [exposure, mul_eq_zero, Real.toNNReal_eq_zero]
  apply or_congr Iff.rfl
  simp only [Wb_coe]
  rw [← W_eq_zero_iff]
  constructor
  · intro h; exact le_antisymm h (W_nonneg _ _ _ _)
  · intro h; exact h.le

/-! ## Session mixtures (Definition 4′, Proposition 7)

A channel's sessions may negotiate different configurations, for example hybrid
for modern clients and classical for legacy ones. Configuration `k` is negotiated
on a share `q k` of the sessions carrying the data class and has break time `T k`.
The share-weighted window is `W̄ = Σ_k q_k · W(T_k)`. -/

section Mix

/-- A channel whose sessions negotiate one of finitely many configurations. -/
structure MixChannel (κ : Type*) where
  O : ℝ≥0
  tfix : ℝ
  H : ℝ
  q : κ → ℝ≥0
  T : κ → WithTop ℝ

variable {κ : Type*} [Fintype κ]

/-- Share-weighted window `W̄ = Σ_k q_k W(T_k)` (Definition 4′). -/
noncomputable def mixW (L : ℝ) (c : MixChannel κ) : ℝ :=
  ∑ k, (c.q k : ℝ) * Wb c.tfix c.H L (c.T k)

lemma mixW_nonneg (L : ℝ) (c : MixChannel κ) : 0 ≤ mixW L c :=
  Finset.sum_nonneg fun k _ => mul_nonneg (c.q k).2 (Wb_nonneg _ _ _ _)

/-- Share-weighted exposure `O · W̄`. -/
noncomputable def mixExposure (L : ℝ) (c : MixChannel κ) : ℝ≥0 :=
  c.O * (mixW L c).toNNReal

/-- Share-weighted HNDL risk over the channel set `s`. -/
noncomputable def mixRisk {ι : Type*} (C : ℝ≥0) (L : ℝ) (ch : ι → MixChannel κ)
    (s : Finset ι) : ℝ≥0 :=
  C * s.sup (fun e => mixExposure L (ch e))

/-- Proposition 7(a), backward compatibility: a channel that always negotiates one
configuration has the exposure of Definition 5. -/
theorem prop7_point_mass (L : ℝ) (c : MixChannel κ) (k0 : κ) (h1 : c.q k0 = 1)
    (h0 : ∀ k, k ≠ k0 → c.q k = 0) :
    mixExposure L c = exposure L ⟨c.O, c.tfix, c.H, c.T k0⟩ := by
  unfold mixExposure exposure mixW
  rw [Finset.sum_eq_single k0 (fun k _ hk => by simp [h0 k hk])
    (fun h => absurd (Finset.mem_univ k0) h)]
  simp [h1]

/-- Proposition 7(b), classical share: if every configuration other than `k0` is
never broken, the window is the classical share times the classical window. -/
theorem prop7_classical_share (L : ℝ) (c : MixChannel κ) (k0 : κ)
    (hsafe : ∀ k, k ≠ k0 → c.T k = ⊤) :
    mixW L c = (c.q k0 : ℝ) * Wb c.tfix c.H L (c.T k0) := by
  unfold mixW
  exact Finset.sum_eq_single k0 (fun k _ hk => by rw [hsafe k hk, Wb_top, mul_zero])
    (fun h => absurd (Finset.mem_univ k0) h)

lemma mixW_le (L : ℝ) (c : MixChannel κ) (M : ℝ) (hM : ∀ k, Wb c.tfix c.H L (c.T k) ≤ M)
    (hq : ∑ k, (c.q k : ℝ) ≤ 1) (hM0 : 0 ≤ M) : mixW L c ≤ M := by
  unfold mixW
  calc ∑ k, (c.q k : ℝ) * Wb c.tfix c.H L (c.T k) ≤ ∑ k, (c.q k : ℝ) * M :=
        Finset.sum_le_sum fun k _ => mul_le_mul_of_nonneg_left (hM k) (c.q k).2
    _ = (∑ k, (c.q k : ℝ)) * M := by rw [Finset.sum_mul]
    _ ≤ 1 * M := mul_le_mul_of_nonneg_right hq hM0
    _ = M := one_mul M

/-- Proposition 7(c), the worst-case reading is an upper bound: if shares sum to at
most one and `Tmin` is no later than any negotiated break time, the share-weighted
exposure is at most the exposure of a channel that always breaks at `Tmin`. -/
theorem prop7_le_worst (L : ℝ) (c : MixChannel κ) (Tmin : WithTop ℝ)
    (hT : ∀ k, Tmin ≤ c.T k) (hq : ∑ k, (c.q k : ℝ) ≤ 1) :
    mixExposure L c ≤ exposure L ⟨c.O, c.tfix, c.H, Tmin⟩ := by
  unfold mixExposure exposure
  apply mul_le_mul' le_rfl
  apply Real.toNNReal_le_toNNReal
  exact mixW_le L c _ (fun k => Wb_mono le_rfl le_rfl le_rfl (hT k)) hq (Wb_nonneg _ _ _ _)

/-- Proposition 7(c), risk form. -/
theorem prop7_risk_le_worst {ι : Type*} (C : ℝ≥0) (L : ℝ) (ch : ι → MixChannel κ)
    (Tmin : ι → WithTop ℝ) (s : Finset ι) (hT : ∀ e ∈ s, ∀ k, Tmin e ≤ (ch e).T k)
    (hq : ∀ e ∈ s, ∑ k, ((ch e).q k : ℝ) ≤ 1) :
    mixRisk C L ch s ≤ risk C L (fun e => ⟨(ch e).O, (ch e).tfix, (ch e).H, Tmin e⟩) s := by
  unfold mixRisk risk
  exact mul_le_mul' le_rfl
    (Finset.sup_mono_fun fun e he => prop7_le_worst L (ch e) (Tmin e) (hT e he) (hq e he))

/-- Mixed-channel order: more observable, later fix, longer history, larger shares,
earlier break for every configuration. -/
def MixChannel.Le (c c' : MixChannel κ) : Prop :=
  c.O ≤ c'.O ∧ c.tfix ≤ c'.tfix ∧ c.H ≤ c'.H ∧ (∀ k, c.q k ≤ c'.q k) ∧ ∀ k, c'.T k ≤ c.T k

lemma mixW_mono {L L' : ℝ} {c c' : MixChannel κ} (hL : L ≤ L') (hc : c.Le c') :
    mixW L c ≤ mixW L' c' := by
  obtain ⟨-, ht, hH, hq, hT⟩ := hc
  unfold mixW
  exact Finset.sum_le_sum fun k _ =>
    mul_le_mul (NNReal.coe_le_coe.mpr (hq k)) (Wb_mono ht hH hL (hT k)) (Wb_nonneg _ _ _ _)
      (c'.q k).2

/-- Proposition 7(d), dominance carries over to the share-weighted reading. -/
theorem prop7_dominance {ι : Type*} (C : ℝ≥0) (L : ℝ) (ch : ι → MixChannel κ)
    {s t : Finset ι} (h : s ⊆ t) : mixRisk C L ch s ≤ mixRisk C L ch t := by
  unfold mixRisk
  exact mul_le_mul' le_rfl (Finset.sup_mono h)

/-- Proposition 7(d), monotonicity: non-decreasing in `C`, `L`, each observability,
remediation time, history and share, non-increasing in each break time, and
non-decreasing when channels are added. -/
theorem prop7_monotone {ι : Type*} {C C' : ℝ≥0} {L L' : ℝ} {ch ch' : ι → MixChannel κ}
    {s t : Finset ι} (hC : C ≤ C') (hL : L ≤ L') (hch : ∀ e ∈ s, (ch e).Le (ch' e))
    (hst : s ⊆ t) : mixRisk C L ch s ≤ mixRisk C' L' ch' t := by
  calc mixRisk C L ch s ≤ mixRisk C' L' ch' s := by
        unfold mixRisk
        apply mul_le_mul' hC
        apply Finset.sup_mono_fun
        intro e he
        unfold mixExposure
        exact mul_le_mul' (hch e he).1 (Real.toNNReal_le_toNNReal (mixW_mono hL (hch e he)))
    _ ≤ mixRisk C' L' ch' t := prop7_dominance C' L' ch' hst

/-- Proposition 7(e), zero window: the share-weighted window vanishes iff every
configuration with a positive share has zero window. -/
theorem prop7_mixW_zero_iff (L : ℝ) (c : MixChannel κ) :
    mixW L c = 0 ↔ ∀ k, c.q k = 0 ∨ Wb c.tfix c.H L (c.T k) = 0 := by
  unfold mixW
  rw [Finset.sum_eq_zero_iff_of_nonneg (s := (Finset.univ : Finset κ))
    (f := fun k => (c.q k : ℝ) * Wb c.tfix c.H L (c.T k))
    (fun k _ => mul_nonneg (c.q k).2 (Wb_nonneg _ _ _ _))]
  simp [mul_eq_zero]

/-- Proposition 7(e), zero risk: the share-weighted analogue of Proposition 3. -/
theorem prop7_zero_iff {ι : Type*} (C : ℝ≥0) (L : ℝ) (ch : ι → MixChannel κ) (s : Finset ι) :
    mixRisk C L ch s = 0 ↔ C = 0 ∨ ∀ e ∈ s, (ch e).O = 0 ∨
      ∀ k, (ch e).q k = 0 ∨ Wb (ch e).tfix (ch e).H L ((ch e).T k) = 0 := by
  unfold mixRisk
  rw [mul_eq_zero]
  apply or_congr Iff.rfl
  rw [← nonpos_iff_eq_zero, Finset.sup_le_iff]
  apply forall₂_congr
  intro e _
  rw [nonpos_iff_eq_zero, mixExposure, mul_eq_zero, Real.toNNReal_eq_zero]
  apply or_congr Iff.rfl
  rw [← prop7_mixW_zero_iff]
  constructor
  · intro h; exact le_antisymm h (mixW_nonneg _ _)
  · intro h; exact h.le

lemma Wb_remediable (tfix H L : ℝ) (T : WithTop ℝ) (ht : 0 ≤ tfix) :
    Wb tfix H L T - Wb 0 H L T = min tfix (Wb tfix H L T) := by
  induction T using WithTop.recTopCoe with
  | top => simp [min_eq_right ht]
  | coe t => simpa using lemma1_remediable tfix H L t ht

/-- Proposition 7(f), sunk and remediable parts mix linearly: the remediable part of
the share-weighted window is `Σ_k q_k min(t_fix, W_k)`. -/
theorem prop7_remediable (L : ℝ) (c : MixChannel κ) (ht : 0 ≤ c.tfix) :
    mixW L c - mixW L ⟨c.O, 0, c.H, c.q, c.T⟩ =
      ∑ k, (c.q k : ℝ) * min c.tfix (Wb c.tfix c.H L (c.T k)) := by
  unfold mixW
  rw [← Finset.sum_sub_distrib]
  refine Finset.sum_congr rfl fun k _ => ?_
  rw [← mul_sub, Wb_remediable _ _ _ _ ht]

end Mix

/-! ## Proposition 4 (fixpoint and condensation)

Channels `e` run from `tail e` (the server holding the data) to `head e` (the caller).
`Xval u` is the maximum edge value over channels whose tail is reachable from `u`. -/

section Fixpoint

open Classical

variable {V ι : Type*} [Fintype ι]

/-- One step along a channel. -/
abbrev Step (tail head : ι → V) (u v : V) : Prop := ∃ e, tail e = u ∧ head e = v

/-- Reachability along channels (reflexive-transitive closure). -/
abbrev Reach (tail head : ι → V) : V → V → Prop := Relation.ReflTransGen (Step tail head)

/-- Propagated value: the maximum of `ω` over channels whose tail is reachable from `u`. -/
noncomputable def Xval (tail head : ι → V) (ω : ι → ℝ≥0) (u : V) : ℝ≥0 :=
  (Finset.univ.filter fun e => Reach tail head u (tail e)).sup ω

/-- The recurrence of §6.4: `F(Y)(u) = max(max_{e=(u→x)} ω(e), max_{e=(u→x)} Y(x))`. -/
noncomputable def recur (tail head : ι → V) (ω : ι → ℝ≥0) (Y : V → ℝ≥0) (u : V) : ℝ≥0 :=
  max ((Finset.univ.filter fun e => tail e = u).sup ω)
      ((Finset.univ.filter fun e => tail e = u).sup fun e => Y (head e))

lemma le_Xval {tail head : ι → V} {ω : ι → ℝ≥0} {u : V} {e : ι}
    (h : Reach tail head u (tail e)) : ω e ≤ Xval tail head ω u :=
  Finset.le_sup (f := ω) (by simp [h])

lemma Xval_anti {tail head : ι → V} {ω : ι → ℝ≥0} {u v : V} (h : Reach tail head u v) :
    Xval tail head ω v ≤ Xval tail head ω u := by
  unfold Xval
  apply Finset.sup_mono
  intro e he
  simp only [Finset.mem_filter, Finset.mem_univ, true_and] at he ⊢
  exact h.trans he

/-- Proposition 4(1): the propagated value is a fixpoint of the recurrence. -/
theorem prop4_fixpoint (tail head : ι → V) (ω : ι → ℝ≥0) :
    recur tail head ω (Xval tail head ω) = Xval tail head ω := by
  funext u
  apply le_antisymm
  · apply max_le
    · apply Finset.sup_le
      intro e he
      simp only [Finset.mem_filter, Finset.mem_univ, true_and] at he
      subst he
      exact le_Xval Relation.ReflTransGen.refl
    · apply Finset.sup_le
      intro e he
      simp only [Finset.mem_filter, Finset.mem_univ, true_and] at he
      exact Xval_anti (Relation.ReflTransGen.single ⟨e, he, rfl⟩)
  · apply Finset.sup_le
    intro e he
    simp only [Finset.mem_filter, Finset.mem_univ, true_and] at he
    rcases Relation.ReflTransGen.cases_head he with h | ⟨c, ⟨e', h1, h2⟩, hc⟩
    · exact le_max_of_le_left (Finset.le_sup (f := ω) (by simp [h]))
    · apply le_max_of_le_right
      calc ω e ≤ Xval tail head ω c := le_Xval hc
        _ = Xval tail head ω (head e') := by rw [h2]
        _ ≤ _ := Finset.le_sup (f := fun e => Xval tail head ω (head e)) (by simp [h1])

/-- Proposition 4(2): it is the least fixpoint; indeed it lies below every
pre-fixpoint `F(Y) ≤ Y`. -/
theorem prop4_least (tail head : ι → V) (ω : ι → ℝ≥0) (Y : V → ℝ≥0)
    (hY : ∀ u, recur tail head ω Y u ≤ Y u) (u : V) : Xval tail head ω u ≤ Y u := by
  apply Finset.sup_le
  intro e he
  simp only [Finset.mem_filter, Finset.mem_univ, true_and] at he
  induction he using Relation.ReflTransGen.head_induction_on with
  | refl =>
    exact (le_max_of_le_left (Finset.le_sup (f := ω) (by simp))).trans (hY _)
  | @head a c hstep _ ih =>
    obtain ⟨e', h1, h2⟩ := hstep
    have hc : Y c ≤ recur tail head ω Y a := by
      rw [← h2]
      exact le_max_of_le_right (Finset.le_sup (f := fun e => Y (head e)) (by simp [h1]))
    exact ih.trans (hc.trans (hY a))

/-- Proposition 4(3): the value is constant on each strongly connected component. -/
theorem prop4_scc (tail head : ι → V) (ω : ι → ℝ≥0) {u v : V}
    (huv : Reach tail head u v) (hvu : Reach tail head v u) :
    Xval tail head ω u = Xval tail head ω v :=
  le_antisymm (Xval_anti hvu) (Xval_anti huv)

/-- Mutual reachability: `w` is in the strongly connected component of `u`. -/
abbrev SameSCC (tail head : ι → V) (u w : V) : Prop := Reach tail head u w ∧ Reach tail head w u

omit [Fintype ι] in
lemma exit_scc {tail head : ι → V} {u w t : V} (hw : SameSCC tail head u w)
    (h : Reach tail head w t) :
    SameSCC tail head u t ∨ ∃ e, SameSCC tail head u (tail e) ∧
      ¬ SameSCC tail head u (head e) ∧ Reach tail head (head e) t := by
  revert hw
  induction h using Relation.ReflTransGen.head_induction_on with
  | refl => exact Or.inl
  | @head a c hstep hrest ih =>
    intro ha
    by_cases hc : SameSCC tail head u c
    · exact ih hc
    · obtain ⟨e, h1, h2⟩ := hstep
      right
      refine ⟨e, ?_, ?_, ?_⟩
      · rw [h1]; exact ha
      · rw [h2]; exact hc
      · rw [h2]; exact hrest

/-- Proposition 4(4), condensation: the value of `u` is the maximum of the edge values
leaving its strongly connected component's members and the values of the components
reached by channels that leave it. This is the recurrence evaluated on the
condensation DAG (Appendix A). -/
theorem prop4_condensation (tail head : ι → V) (ω : ι → ℝ≥0) (u : V) :
    Xval tail head ω u =
      max ((Finset.univ.filter fun e => SameSCC tail head u (tail e)).sup ω)
          ((Finset.univ.filter fun e => SameSCC tail head u (tail e) ∧
              ¬ SameSCC tail head u (head e)).sup fun e => Xval tail head ω (head e)) := by
  apply le_antisymm
  · apply Finset.sup_le
    intro e he
    simp only [Finset.mem_filter, Finset.mem_univ, true_and] at he
    rcases exit_scc ⟨Relation.ReflTransGen.refl, Relation.ReflTransGen.refl⟩ he with
      h | ⟨e', h1, h2, h3⟩
    · exact le_max_of_le_left (Finset.le_sup (f := ω) (Finset.mem_filter.mpr ⟨Finset.mem_univ _, h⟩))
    · exact le_max_of_le_right ((le_Xval h3).trans
        (Finset.le_sup (f := fun e => Xval tail head ω (head e))
          (Finset.mem_filter.mpr ⟨Finset.mem_univ _, h1, h2⟩)))
  · apply max_le
    · apply Finset.sup_le
      intro e he
      simp only [Finset.mem_filter, Finset.mem_univ, true_and] at he
      exact le_Xval he.1
    · apply Finset.sup_le
      intro e he
      simp only [Finset.mem_filter, Finset.mem_univ, true_and] at he
      exact Xval_anti (he.1.1.tail ⟨e, rfl, rfl⟩)

end Fixpoint

/-! ## Expectation forms of Propositions 1–3

Channel parameters, in particular break times, may depend on the realization `ω`
of the CRQC arrival; the risk of Definition 5 is the expectation of the
per-realization risk. -/

section Expectation

open MeasureTheory ENNReal

variable {Ω : Type*} [MeasurableSpace Ω] {ι : Type*}

/-- Expected HNDL risk `E[C · max_e O(e) W_e(d)]`. -/
noncomputable def expRisk (μ : Measure Ω) (C : ℝ≥0) (L : ℝ) (ch : Ω → ι → Channel)
    (s : Finset ι) : ℝ≥0∞ :=
  ∫⁻ ω, (risk C L (ch ω) s : ℝ≥0∞) ∂μ

/-- Proposition 1, expectation form. -/
theorem prop1_expected (μ : Measure Ω) (C : ℝ≥0) (L : ℝ) (ch : Ω → ι → Channel)
    {s t : Finset ι} (h : s ⊆ t) : expRisk μ C L ch s ≤ expRisk μ C L ch t :=
  lintegral_mono fun ω => ENNReal.coe_le_coe.mpr (prop1_dominance C L (ch ω) h)

/-- Proposition 2, expectation form (orders hold for every realization). -/
theorem prop2_expected (μ : Measure Ω) {C C' : ℝ≥0} {L L' : ℝ} {ch ch' : Ω → ι → Channel}
    {s t : Finset ι} (hC : C ≤ C') (hL : L ≤ L') (hch : ∀ ω, ∀ e ∈ s, (ch ω e).Le (ch' ω e))
    (hst : s ⊆ t) : expRisk μ C L ch s ≤ expRisk μ C' L' ch' t :=
  lintegral_mono fun ω => ENNReal.coe_le_coe.mpr (prop2_monotone hC hL (hch ω) hst)

/-- Proposition 3, expectation form: expected risk is zero iff, almost surely, the
criticality is zero or every channel is unobservable or has a zero window. -/
theorem prop3_expected (μ : Measure Ω) (C : ℝ≥0) (L : ℝ) (ch : Ω → ι → Channel)
    (s : Finset ι) (hm : AEMeasurable (fun ω => (risk C L (ch ω) s : ℝ≥0∞)) μ) :
    expRisk μ C L ch s = 0 ↔ ∀ᵐ ω ∂μ, C = 0 ∨ ∀ e ∈ s, (ch ω e).O = 0 ∨
      Wb (ch ω e).tfix (ch ω e).H L (ch ω e).T = 0 := by
  unfold expRisk
  rw [lintegral_eq_zero_iff' hm]
  refine Filter.eventually_congr (Filter.Eventually.of_forall fun ω => ?_)
  simp only [Pi.zero_apply, ENNReal.coe_eq_zero]
  exact prop3_zero_iff C L (ch ω) s

end Expectation

/-! ## Proposition 6 (layer cake) and Corollary 1 -/

section LayerCake

open MeasureTheory Set ENNReal

lemma ofReal_max_zero (x : ℝ) : ENNReal.ofReal (max 0 x) = ENNReal.ofReal x := by
  rcases le_total 0 x with h | h
  · rw [max_eq_right h]
  · rw [max_eq_left h, ENNReal.ofReal_zero, ENNReal.ofReal_of_nonpos h]

/-- Proposition 6: for a non-negative random break time `T` and `a = t_fix + L`,
`E[(a − T)⁺] = ∫₀^a P[T < s] ds`. (`P[T < s]` and `F(s) = P[T ≤ s]` differ for at most
countably many `s`, so the integral is the same.) -/
theorem prop6_layercake {Ω : Type*} [MeasurableSpace Ω] (μ : Measure Ω) (T : Ω → ℝ)
    (hT : Measurable T) (hT0 : ∀ ω, 0 ≤ T ω) (a : ℝ) :
    ∫⁻ ω, ENNReal.ofReal (a - T ω) ∂μ = ∫⁻ s in Ioo 0 a, μ {ω | T ω < s} := by
  have hsub : Measurable fun ω => a - T ω := measurable_const.sub hT
  have hf : Measurable fun ω => max 0 (a - T ω) := measurable_const.max hsub
  have h1 := lintegral_eq_lintegral_meas_lt μ
    (Filter.Eventually.of_forall fun ω => le_max_left 0 (a - T ω)) hf.aemeasurable
  simp only [ofReal_max_zero] at h1
  rw [h1]
  -- for t > 0: t < max 0 (a - T) ↔ T < a - t
  have h2 : ∫⁻ t in Ioi 0, μ {ω | t < max 0 (a - T ω)} =
      ∫⁻ t in Ioi 0, (Ioo 0 a).indicator (fun t => μ {ω | T ω < a - t}) t := by
    apply setLIntegral_congr_fun measurableSet_Ioi
    intro t ht
    have ht' : (0 : ℝ) < t := ht
    by_cases hta : t < a
    · rw [Set.indicator_of_mem (show t ∈ Ioo 0 a from ⟨ht', hta⟩)]
      refine congrArg μ (Set.ext fun ω => ?_)
      simp only [Set.mem_ofPred_eq, lt_max_iff]
      constructor
      · rintro (h | h)
        · exact absurd h (not_lt.mpr ht'.le)
        · linarith
      · intro h; right; linarith
    · rw [Set.indicator_of_notMem (show t ∉ Ioo 0 a from fun h => hta h.2)]
      convert measure_empty (μ := μ)
      ext ω
      simp only [Set.mem_ofPred_eq, lt_max_iff, Set.mem_empty_iff_false, iff_false, not_or, not_lt]
      exact ⟨ht'.le, by linarith [hT0 ω, not_lt.mp hta]⟩
  rw [h2, setLIntegral_indicator measurableSet_Ioo, Set.inter_eq_left.mpr Set.Ioo_subset_Ioi_self]
  -- reflect t ↦ a - t, which maps `Ioo 0 a` onto itself and preserves Lebesgue measure
  have hpre : (fun t => a - t) ⁻¹' Ioo 0 a = Ioo 0 a := by
    ext t
    simp only [Set.mem_preimage, Set.mem_Ioo]
    constructor <;> rintro ⟨h1, h2⟩ <;> constructor <;> linarith
  have h3 := (volume.measurePreserving_sub_left a).setLIntegral_comp_preimage_emb
    (measurableEmbedding_subLeft a) (fun s => μ {ω | T ω < s}) (Ioo 0 a)
  rw [hpre] at h3
  exact h3

/-- Corollary 1: for a hybrid with break time `max(T_Q, T_PQ)`, the expected window is
`∫₀^a P[T_Q < s ∧ T_PQ < s] ds`. -/
theorem cor1_hybrid {Ω : Type*} [MeasurableSpace Ω] (μ : Measure Ω) (TQ TPQ : Ω → ℝ)
    (hQ : Measurable TQ) (hP : Measurable TPQ) (hQ0 : ∀ ω, 0 ≤ TQ ω) (a : ℝ) :
    ∫⁻ ω, ENNReal.ofReal (a - max (TQ ω) (TPQ ω)) ∂μ =
      ∫⁻ s in Ioo 0 a, μ ({ω | TQ ω < s} ∩ {ω | TPQ ω < s}) := by
  rw [prop6_layercake μ _ (hQ.max hP) (fun ω => (hQ0 ω).trans (le_max_left _ _)) a]
  congr 1
  funext s
  congr 1
  ext ω
  simp [max_lt_iff]

/-- Corollary 1, upper Fréchet bound (no independence needed). -/
theorem cor1_upper {Ω : Type*} [MeasurableSpace Ω] (μ : Measure Ω) (TQ TPQ : Ω → ℝ) (s : ℝ) :
    μ ({ω | TQ ω < s} ∩ {ω | TPQ ω < s}) ≤ min (μ {ω | TQ ω < s}) (μ {ω | TPQ ω < s}) :=
  le_min (measure_mono Set.inter_subset_left) (measure_mono Set.inter_subset_right)

end LayerCake

/-! ## Proposition 8 (non-submodularity), concrete counterexample

Two channels carry one data class, each with window 7 and sunk window 5.
Fixing a set `S` of channels now drops each fixed channel's window to 5. -/

/-- Worst-case window after fixing the channels in `S`. -/
def worstAfter (S : Finset (Fin 2)) : ℕ :=
  (Finset.univ : Finset (Fin 2)).sup fun e => if e ∈ S then 5 else 7

/-- Risk reduction obtained by fixing `S`. -/
def reduction (S : Finset (Fin 2)) : ℕ := 7 - worstAfter S

theorem prop8_values :
    reduction ∅ = 0 ∧ reduction {0} = 0 ∧ reduction {1} = 0 ∧ reduction {0, 1} = 2 := by
  decide

/-- Proposition 8: risk reduction is not submodular, since
`g(A) + g(B) < g(A ∪ B) + g(A ∩ B)` for `A = {0}`, `B = {1}`. -/
theorem prop8_not_submodular :
    ¬ ∀ A B : Finset (Fin 2), reduction (A ∪ B) + reduction (A ∩ B) ≤ reduction A + reduction B := by
  intro h
  have := h {0} {1}
  revert this
  decide

-- BEGIN GENERATED TEST VECTORS
/-! Test vectors shared with `testbed/tests/vectors.json`; each value is also checked
against the scorer `tools/score.py` by `testbed/tests/test_properties.py`. -/

/-- gw->client, records, T_Q = 10 (Table 6) -/
theorem vec_edge_tq10 : W 1 20 15 10 = 6 := by
  norm_num [W, max_def]

/-- lb->gw, records, T_Q = 10 -/
theorem vec_lb_tq10 : W 2 20 15 10 = 7 := by
  norm_num [W, max_def]

/-- sunk window of lb->gw -/
theorem vec_lb_sunk_tq10 : W 0 20 15 10 = 5 := by
  norm_num [W, max_def]

/-- records, T_Q = 5 -/
theorem vec_edge_tq5 : W 1 20 15 5 = 11 := by
  norm_num [W, max_def]

/-- records, T_Q = 15: remediable part only -/
theorem vec_edge_tq15 : W 1 20 15 15 = 1 := by
  norm_num [W, max_def]

/-- break after the data stops being sensitive -/
theorem vec_edge_tq20 : W 1 20 15 20 = 0 := by
  norm_num [W, max_def]

/-- history shorter than L - T -/
theorem vec_short_history : W 2 3 15 5 = 5 := by
  norm_num [W, max_def]

/-- profile, T_Q = 10 -/
theorem vec_profile_tq10 : W 1 20 8 10 = 0 := by
  norm_num [W, max_def]

/-- classically broken layer, T = 0 -/
theorem vec_broken_now : W 1 20 8 0 = 9 := by
  norm_num [W, max_def]

/-- fixed now with no recorded history -/
theorem vec_no_history : W 0 0 15 5 = 0 := by
  norm_num [W, max_def]

-- END GENERATED TEST VECTORS

end TopoPQC
