/**
 * Step15Wizard — adapter shim between App.tsx routing props and Step15Capacitor.
 */
import React from 'react'
import { Step15Capacitor } from './Step15Capacitor'
import type { CapacitorResult } from './Step15Capacitor'

interface Props {
  confirmedState:   Record<string, unknown>
  approvedDesign:   Record<string, unknown>
  onBack:           () => void
  onRestart:        () => void
  onApprove:        (result: CapacitorResult) => void
}

export const Step15Wizard: React.FC<Props> = ({
  confirmedState, approvedDesign, onBack, onRestart, onApprove,
}) => (
  <Step15Capacitor
    confirmedState={confirmedState}
    approvedDesign={approvedDesign}
    onConfirm={onApprove}
    onBack={onBack}
  />
)
